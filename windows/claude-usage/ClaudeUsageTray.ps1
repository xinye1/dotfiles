<#
.SYNOPSIS
Claude Code usage in the Windows notification area, fed from WSL.

.DESCRIPTION
The Windows face of waybar's claude widget (PLAYBOOK §9.31). Every decision -
the API fetch and its TTL, the transcript scan, the rounded percent and its
70/90 level, labels, pace windows, day buckets - stays in claude_usage.py
inside WSL, under its own tests. This script only asks it for a snapshot
(`--json`) and turns that into pixels: a tray icon carrying the worst percent,
a hover summary, and a click-open panel. The countdowns and the pace marker
are computed here against this machine's clock, from the epoch times in the
snapshot, so an open panel or a snapshot taken before WSL went idle never shows
a countdown that has stopped.

Installed and kept up to date by windows/claude-usage/install.py, which copies
this file to %LOCALAPPDATA%\ClaudeUsage next to the config.json it writes.

.PARAMETER Library
Define the functions and return without starting anything: the seam
tests/claude_tray_test.ps1 dot-sources.

.PARAMETER RenderPanel
Draw the panel for the snapshot in -Snapshot to this PNG and exit. How the
layout is checked by eye without a desktop session, and how the tests check
that painting a real snapshot does not throw.
#>
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'config.json'),
    [switch]$Library,
    [string]$RenderPanel,
    [string]$RenderIcon,
    [string]$Snapshot,
    [switch]$Idle
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$SnapshotSchema = 1        # claude_usage.SNAPSHOT_SCHEMA; refuse any other
$HoverMax = 63             # NotifyIcon.Text throws past 63 on .NET Framework
$UsageUrl = 'https://claude.ai/settings/usage'

# .NET named colours only, for the same reason FALLBACK_THEME in
# claude_usage.py uses Pango names: tests/check_hex.py rejects a literal hex in
# any tracked file. The real palette arrives in config.json, rendered by
# install.py from palettes.toml - this is only what a missing role falls to.
$FallbackTheme = @{
    bg = 'Black'; surface = 'Black'; sel = 'DimGray'; muted = 'Gray'
    dim = 'Silver'; fg = 'White'; fg_bright = 'White'; accent = 'Gold'
    indicator = 'LightGreen'; critical = 'Tomato'; warning = 'Orange'
}

# --- pure helpers (tests/claude_tray_test.ps1) -------------------------------

function Get-NowEpoch {
    [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
}

function ConvertTo-LocalTime([double]$Epoch) {
    [DateTimeOffset]::FromUnixTimeMilliseconds([long]($Epoch * 1000)).LocalDateTime
}

function Format-Countdown($ResetsAt, [double]$Now) {
    # claude_usage.countdown()'s format, from an epoch instead of an ISO
    # string: "4d 22h", "3h 13m", "5m", "now", or "" when there is no reset.
    if ($null -eq $ResetsAt) { return '' }
    $mins = [long][Math]::Floor(([double]$ResetsAt - $Now) / 60)
    if ($mins -le 0) { return 'now' }
    $d = [Math]::Floor($mins / 1440); $h = [Math]::Floor(($mins % 1440) / 60); $m = $mins % 60
    if ($d -gt 0) { return "${d}d ${h}h" }
    if ($h -gt 0) { return "${h}h ${m}m" }
    return "${m}m"
}

function Get-PaceFraction($Limit, [double]$Now) {
    # How far through its window a limit is, clamped to 0..1, or $null when
    # the snapshot could not establish the window (claude_usage.pace_window).
    $start = $Limit.window_start; $end = $Limit.resets_at
    if ($null -eq $start -or $null -eq $end -or [double]$end -le [double]$start) { return $null }
    $f = ($Now - [double]$start) / ([double]$end - [double]$start)
    return [Math]::Min([Math]::Max($f, 0.0), 1.0)
}

function Get-OptionalValue($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p -or $null -eq $p.Value) { return $Default }
    return $p.Value
}

function ConvertFrom-Snapshot([string]$Json) {
    # Snapshot JSON -> hashtables with every key present, so nothing past this
    # point can trip StrictMode on a missing property. Throws on a schema this
    # script does not know: drawing half of a changed shape is worse than
    # saying so.
    $o = $Json | ConvertFrom-Json
    $schema = Get-OptionalValue $o 'schema'
    if ($schema -ne $SnapshotSchema) {
        throw "snapshot schema $schema, this tray reads $SnapshotSchema (re-run install.py)"
    }
    $num = { param($v) if ($null -eq $v) { $null } else { [double]$v } }
    $limits = @(foreach ($l in @(Get-OptionalValue $o 'limits' @() | Where-Object { $null -ne $_ })) {
        @{
            label        = [string](Get-OptionalValue $l 'label' '?')
            shown        = [int](Get-OptionalValue $l 'shown' 0)
            fill         = [double](Get-OptionalValue $l 'fill' 0)
            level        = [string](Get-OptionalValue $l 'level' 'normal')
            resets_at    = & $num (Get-OptionalValue $l 'resets_at')
            window_start = & $num (Get-OptionalValue $l 'window_start')
        }
    })
    $series = {
        param($items, $key)
        # A missing list arrives as $null, not @(): PowerShell unrolls an
        # empty array on its way out of Get-OptionalValue, and @($null) is a
        # one-element array. Hence the filter.
        @(foreach ($i in @($items | Where-Object { $null -ne $_ })) {
            @{ $key = [string](Get-OptionalValue $i $key '')
               tokens = [double](Get-OptionalValue $i 'tokens' 0)
               human = [string](Get-OptionalValue $i 'human' '0') }
        })
    }
    return @{
        generated_at = [double](Get-OptionalValue $o 'generated_at' 0)
        tier         = [string](Get-OptionalValue $o 'tier' '')
        level        = [string](Get-OptionalValue $o 'level' 'stale')
        error        = Get-OptionalValue $o 'error'
        fetched_at   = & $num (Get-OptionalValue $o 'fetched_at')
        limits       = $limits
        days         = & $series (Get-OptionalValue $o 'days' @()) 'date'
        models       = & $series (Get-OptionalValue $o 'models' @()) 'name'
    }
}

function Format-Clock($Epoch) {
    if ($null -eq $Epoch) { return 'never' }
    return (ConvertTo-LocalTime $Epoch).ToString('HH:mm')
}

function Get-DayLabel([string]$Date, [datetime]$Today) {
    $d = [datetime]::ParseExact($Date, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture)
    if ($d.Date -eq $Today.Date) { return 'Today' }
    return $d.ToString('ddd', [Globalization.CultureInfo]::InvariantCulture)
}

function Get-IconText($Snap) {
    # The worst displayed percent, the number waybar's bar stacks first among
    # equals; an en dash before there is anything to show.
    if ($null -eq $Snap -or @($Snap.limits).Count -eq 0) { return [string][char]0x2013 }
    return [string](@($Snap.limits | ForEach-Object { $_.shown }) | Measure-Object -Maximum).Maximum
}

function Get-IconLevel($Snap, [bool]$Idle, [string]$Fault) {
    # The icon's fill. Anything that makes the number less than current - an
    # API error, a failed collector run, WSL asleep - greys it, like waybar's
    # `stale` class; the number stays, so last-known is still readable.
    if ($null -eq $Snap -or $Fault -or $Idle -or $Snap.level -eq 'stale') { return 'stale' }
    return $Snap.level
}

function Get-StatusLine($Snap, [bool]$Idle, [string]$Fault) {
    if ($Fault) { return "error: $Fault" }
    if ($null -eq $Snap) { return $(if ($Idle) { 'WSL idle, no data yet' } else { 'no data yet' }) }
    if ($Snap.error) { return "stale: $($Snap.error)" }
    if ($Idle) { return "WSL idle since $(Format-Clock $Snap.generated_at)" }
    return ''
}

function Get-HoverText($Snap, [double]$Now, [bool]$Idle, [string]$Fault) {
    # At most $HoverMax characters, shedding detail in a fixed order rather
    # than truncating mid-word: countdowns go first, the status line second.
    $status = Get-StatusLine $Snap $Idle $Fault
    $rows = @(if ($null -ne $Snap) { $Snap.limits })
    if ($rows.Count -eq 0) {
        $text = 'Claude usage' + $(if ($status) { ": $status" } else { '' })
    } else {
        $full = @($rows | ForEach-Object {
            $c = Format-Countdown $_.resets_at $Now
            "$($_.label) $($_.shown)%" + $(if ($c) { " $([char]0x00B7) $c" } else { '' })
        })
        $bare = @($rows | ForEach-Object { "$($_.label) $($_.shown)%" })
        $text = $null
        for ($i = 0; $i -lt 3 -and $null -eq $text; $i++) {
            $lines = switch ($i) { 0 { @($full) + @($status) } 1 { @($bare) + @($status) } 2 { @($bare) } }
            $candidate = (@($lines) | Where-Object { $_ }) -join "`n"
            if ($candidate.Length -le $HoverMax) { $text = $candidate }
        }
        if ($null -eq $text) { $text = $bare -join ' ' }
    }
    if ($text.Length -gt $HoverMax) { $text = $text.Substring(0, $HoverMax - 1) + [char]0x2026 }
    return $text
}

function Test-DistroRunning([string[]]$ListOutput, [string]$Distro) {
    # `wsl.exe --list --running --quiet` under WSL_UTF8=1: one name per line,
    # or an English sentence when nothing runs. Exact, case-insensitive match
    # so "Ubuntu" is not running just because "Ubuntu-24.04" is.
    foreach ($line in @($ListOutput)) {
        if ($null -ne $line -and $line.Trim().Trim([char]0) -ieq $Distro) { return $true }
    }
    return $false
}

function ConvertTo-ArgumentString([string[]]$Arguments) {
    # Windows command-line quoting for ProcessStartInfo.Arguments: wsl.exe
    # --exec hands each argument to the Linux process as-is, so a script path
    # with spaces must arrive as one argv entry.
    (@($Arguments) | ForEach-Object {
        if ($_ -match '[\s"]' -or $_ -eq '') { '"' + ($_ -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"' } else { $_ }
    }) -join ' '
}

function Get-Theme($Config) {
    $theme = @{}
    foreach ($k in $FallbackTheme.Keys) { $theme[$k] = [Drawing.Color]::FromName($FallbackTheme[$k]) }
    $given = Get-OptionalValue $Config 'theme'
    if ($null -ne $given) {
        foreach ($p in $given.PSObject.Properties) {
            try { $theme[$p.Name] = [Drawing.ColorTranslator]::FromHtml([string]$p.Value) } catch { }
        }
    }
    return $theme
}

function Get-LevelColor($Theme, [string]$Level) {
    switch ($Level) {
        'critical' { return $Theme.critical }
        'warning' { return $Theme.warning }
        'stale' { return $Theme.muted }
        default { return $Theme.indicator }
    }
}

# --- panel layout -------------------------------------------------------------
# Layout is a list of draw operations with absolute positions, built once per
# data change and replayed on every paint. Building it measures text but never
# needs a window, which is what lets -RenderPanel draw to a PNG.

function New-Fonts([double]$Scale) {
    # Points scale with the DPI GDI draws at; $Scale is for pixel distances.
    @{
        body    = New-Object Drawing.Font('Segoe UI', 9)
        bold    = New-Object Drawing.Font('Segoe UI Semibold', 9)
        title   = New-Object Drawing.Font('Segoe UI Semibold', 10)
        section = New-Object Drawing.Font('Segoe UI Semibold', 7.5)
        small   = New-Object Drawing.Font('Segoe UI', 8)
    }
}

$TextFlags = [Windows.Forms.TextFormatFlags]'NoPadding, NoPrefix, SingleLine'

function Measure-Width([string]$Text, $Font) {
    if (-not $Text) { return 0 }
    [Windows.Forms.TextRenderer]::MeasureText($Text, $Font, (New-Object Drawing.Size(4096, 512)), $TextFlags).Width
}

function Get-PanelLayout($Snap, $Theme, $Fonts, [double]$Scale, [double]$Now, [bool]$Idle, [string]$Fault) {
    $s = $Scale
    $pad = [int](16 * $s); $gap = [int](10 * $s)
    $lineH = [int]($Fonts.body.Height + 6 * $s)
    $ops = New-Object Collections.ArrayList
    $y = $pad
    $text = { param($x, $y, $str, $font, $color, $right = 0)
        [void]$ops.Add(@{ kind = 'text'; x = $x; y = $y; text = $str; font = $font; color = $color; right = $right }) }
    $rect = { param($x, $y, $w, $h, $color)
        [void]$ops.Add(@{ kind = 'rect'; x = $x; y = $y; w = $w; h = $h; color = $color }) }

    # Column geometry for the limit rows first: it sets the panel width that
    # every other row then fills.
    $limits = @(if ($null -ne $Snap) { $Snap.limits })
    $labelW = 0; foreach ($l in $limits) { $labelW = [Math]::Max($labelW, (Measure-Width $l.label $Fonts.body)) }
    $barW = [int](150 * $s)
    $pctW = Measure-Width '100%' $Fonts.bold
    $cdW = 0; foreach ($l in $limits) {
        $c = Format-Countdown $l.resets_at $Now
        if ($c) { $cdW = [Math]::Max($cdW, (Measure-Width "resets in $c" $Fonts.small)) }
    }
    $width = $pad + $labelW + $gap + $barW + $gap + $pctW + $(if ($cdW) { $gap + $cdW } else { 0 }) + $pad

    $tier = if ($null -ne $Snap -and $Snap.tier) { "$([char]0x00B7) $($Snap.tier)" } else { '' }
    $tierGap = [int](6 * $s)
    $banners = @()
    if ($Fault) { $banners += , @("$([char]0x26A0) $Fault", $Theme.critical) }
    if ($null -ne $Snap -and $Snap.error) {
        $banners += , @("$([char]0x26A0) stale $([char]0x2014) $($Snap.error), data from $(Format-Clock $Snap.fetched_at)", $Theme.warning)
    }
    if ($Idle) {
        $what = if ($null -ne $Snap) { "showing data from $(Format-Clock $Snap.generated_at)" } else { 'right-click the icon, Refresh now, to start it' }
        $banners += , @("WSL is not running $([char]0x2014) $what", $Theme.dim)
    }
    $footer = if ($null -ne $Snap -and $null -ne $Snap.fetched_at) { "updated $(Format-Clock $Snap.fetched_at)" } else { 'not updated yet' }
    $footer += " $([char]0x00B7) right-click the icon for options"
    $width = [Math]::Max($width, $pad + (Measure-Width 'Claude Code' $Fonts.title) + $tierGap + (Measure-Width $tier $Fonts.small) + $pad)
    foreach ($b in $banners) { $width = [Math]::Max($width, $pad + (Measure-Width $b[0] $Fonts.small) + $pad) }
    $width = [Math]::Max($width, $pad + (Measure-Width $footer $Fonts.small) + $pad)
    $width = [Math]::Max($width, [int](300 * $s))

    & $text $pad $y 'Claude Code' $Fonts.title $Theme.fg_bright
    if ($tier) {
        # Baselines aligned: the smaller font starts lower by the ascent gap.
        $drop = [int]($Fonts.title.FontFamily.GetCellAscent('Regular') * $Fonts.title.Size / $Fonts.title.FontFamily.GetEmHeight('Regular') -
                      $Fonts.small.FontFamily.GetCellAscent('Regular') * $Fonts.small.Size / $Fonts.small.FontFamily.GetEmHeight('Regular')) * 96 / 72 * $s
        & $text ($pad + (Measure-Width 'Claude Code' $Fonts.title) + $tierGap) ($y + [int]$drop) $tier $Fonts.small $Theme.dim
    }
    $y += $Fonts.title.Height + [int](4 * $s)
    foreach ($b in $banners) {
        $y += [int](4 * $s)
        & $text $pad $y $b[0] $Fonts.small $b[1]
        $y += $Fonts.small.Height
    }

    # Scriptblocks invoked with & get a child scope, so a plain `$y +=` inside
    # one would vanish on return; the cursor is a hashtable they all mutate.
    $cur = @{ y = $y }
    $section = { param($title)
        $cur.y += $gap
        & $text $pad $cur.y $title $Fonts.section $Theme.accent
        $cur.y += $Fonts.section.Height + [int](4 * $s)
    }

    if ($limits.Count -gt 0) {
        & $section 'LIMITS'
        $marked = $false
        $barH = [int](8 * $s); $barX = $pad + $labelW + $gap
        foreach ($l in $limits) {
            $y = $cur.y
            $fillColor = Get-LevelColor $Theme $l.level
            & $text $pad $y $l.label $Fonts.body $Theme.fg
            $by = $y + [int](($Fonts.body.Height - $barH) / 2)
            & $rect $barX $by $barW $barH $Theme.sel
            $fw = [int]($barW * [Math]::Min([Math]::Max($l.fill, 0.0), 1.0))
            if ($fw -gt 0) { & $rect $barX $by $fw $barH $fillColor }
            $pace = Get-PaceFraction $l $Now
            if ($null -ne $pace) {
                $marked = $true
                $mw = [Math]::Max(2, [int](2 * $s))
                $mx = $barX + [int](($barW - $mw) * $pace)
                & $rect $mx ($by - [int](3 * $s)) $mw ($barH + [int](6 * $s)) $Theme.fg_bright
            }
            $pctRight = $barX + $barW + $gap + $pctW
            & $text 0 $y "$($l.shown)%" $Fonts.bold $fillColor $pctRight
            $c = Format-Countdown $l.resets_at $Now
            if ($c) { & $text ($pctRight + $gap) ($y + [int](1 * $s)) "resets in $c" $Fonts.small $Theme.dim }
            $cur.y += $lineH
        }
        if ($marked) {
            $y = $cur.y
            $mw = [Math]::Max(2, [int](2 * $s))
            & $rect $pad ($y + [int](1 * $s)) $mw ($Fonts.small.Height - [int](2 * $s)) $Theme.fg_bright
            & $text ($pad + $mw + [int](5 * $s)) $y "now $([char]0x00B7) fill past it = ahead of pace" $Fonts.small $Theme.dim
            $cur.y += $Fonts.small.Height + [int](2 * $s)
        }
    } elseif ($null -ne $Snap -and -not $Snap.error) {
        $cur.y += $gap
        & $text $pad $cur.y 'no limit data yet' $Fonts.small $Theme.dim
        $cur.y += $Fonts.small.Height
    }

    # Both charts share one label and one value column, so their bars start
    # and end on the same x and read as one table.
    # From $Now, never the wall clock: the panel is a pure function of what it
    # is handed, which is what lets the tests pin it to a fixture's date.
    $today = (ConvertTo-LocalTime $Now).Date
    $dayRows = @(if ($null -ne $Snap) { $Snap.days })
    $modelRows = @(if ($null -ne $Snap) { $Snap.models })
    $lw = 0; $vw = 0
    foreach ($r in $dayRows) { $lw = [Math]::Max($lw, (Measure-Width (Get-DayLabel $r.date $today) $Fonts.bold)) }
    foreach ($r in $modelRows) { $lw = [Math]::Max($lw, (Measure-Width $r.name $Fonts.bold)) }
    foreach ($r in @($dayRows) + @($modelRows)) { $vw = [Math]::Max($vw, (Measure-Width $r.human $Fonts.body)) }
    $chart = { param($title, $rows, $labelOf, $strongOf)
        & $section $title
        $peak = 1.0
        foreach ($r in $rows) { $peak = [Math]::Max($peak, $r.tokens) }
        $bx = $pad + $lw + $gap; $bw = $width - $pad - $vw - $gap - $bx
        $bh = [int](8 * $s)
        foreach ($r in $rows) {
            $y = $cur.y
            $strong = & $strongOf $r
            & $text $pad $y (& $labelOf $r) $(if ($strong) { $Fonts.bold } else { $Fonts.body }) $(if ($strong) { $Theme.fg } else { $Theme.dim })
            $w = [Math]::Max([int]($bw * $r.tokens / $peak), [Math]::Max(1, [int]$s))
            & $rect $bx ($y + [int](($Fonts.body.Height - $bh) / 2)) $w $bh $Theme.indicator
            & $text 0 $y $r.human $Fonts.body $Theme.fg ($width - $pad)
            $cur.y += $lineH
        }
    }
    if ($dayRows.Count -gt 0) {
        & $chart 'TOKENS BY DAY' $dayRows { param($r) Get-DayLabel $r.date $today } { param($r) (Get-DayLabel $r.date $today) -eq 'Today' }
        if ($modelRows.Count -gt 0) {
            & $chart 'TOKENS BY MODEL (7d)' $modelRows { param($r) $r.name } { param($r) $false }
        }
    }

    $y = $cur.y + $gap
    & $text $pad $y $footer $Fonts.small $Theme.dim
    $height = $y + $Fonts.small.Height + $pad
    return @{ ops = $ops; width = [int]$width; height = [int]$height }
}

function Invoke-PanelPaint([Drawing.Graphics]$G, $Layout, $Theme) {
    $G.Clear($Theme.bg)
    $G.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::None
    $border = New-Object Drawing.Pen($Theme.muted)
    try { $G.DrawRectangle($border, 0, 0, $Layout.width - 1, $Layout.height - 1) } finally { $border.Dispose() }
    foreach ($op in $Layout.ops) {
        if ($op.kind -eq 'rect') {
            $b = New-Object Drawing.SolidBrush($op.color)
            try { $G.FillRectangle($b, $op.x, $op.y, $op.w, $op.h) } finally { $b.Dispose() }
        } elseif ($op.right) {
            $w = Measure-Width $op.text $op.font
            [Windows.Forms.TextRenderer]::DrawText($G, $op.text, $op.font, (New-Object Drawing.Point(($op.right - $w), $op.y)), $op.color, $TextFlags)
        } else {
            [Windows.Forms.TextRenderer]::DrawText($G, $op.text, $op.font, (New-Object Drawing.Point($op.x, $op.y)), $op.color, $TextFlags)
        }
    }
}

function New-IconBitmap([string]$Text, [Drawing.Color]$Fill, [Drawing.Color]$Ink, [int]$Size) {
    # A rounded tile in the level colour carrying the number. The font is the
    # largest that fits, so "7" is big and "100" still fits a 16px icon.
    $bmp = New-Object Drawing.Bitmap($Size, $Size)
    $g = [Drawing.Graphics]::FromImage($bmp)
    try {
        $g.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
        $r = [Math]::Max(2, [int]($Size / 4)); $d = 2 * $r
        $path = New-Object Drawing.Drawing2D.GraphicsPath
        $path.AddArc(0, 0, $d, $d, 180, 90); $path.AddArc($Size - $d - 1, 0, $d, $d, 270, 90)
        $path.AddArc($Size - $d - 1, $Size - $d - 1, $d, $d, 0, 90); $path.AddArc(0, $Size - $d - 1, $d, $d, 90, 90)
        $path.CloseFigure()
        $brush = New-Object Drawing.SolidBrush($Fill); $g.FillPath($brush, $path); $brush.Dispose(); $path.Dispose()
        $fmt = New-Object Drawing.StringFormat
        $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
        $em = $Size * 0.8
        do {
            $font = New-Object Drawing.Font('Segoe UI', [single]$em, [Drawing.FontStyle]::Bold, [Drawing.GraphicsUnit]::Pixel)
            $fits = $g.MeasureString($Text, $font, 1000, [Drawing.StringFormat]::GenericTypographic).Width -le ($Size - 1)
            if (-not $fits) { $font.Dispose(); $em -= 0.5 }
        } while (-not $fits -and $em -gt 4)
        $inkBrush = New-Object Drawing.SolidBrush($Ink)
        $g.DrawString($Text, $font, $inkBrush, (New-Object Drawing.RectangleF(0, 0.5, $Size, $Size)), $fmt)
        $inkBrush.Dispose(); $font.Dispose(); $fmt.Dispose()
    } finally { $g.Dispose() }
    return $bmp
}

# --- notifications ----------------------------------------------------------------
# A toast when a limit climbs into a higher band - 70% (warning), 90%
# (critical), 100% (reached), the first two being claude_usage.level_of()'s -
# and when a limit that had reached a band rolls over into a fresh window.
# State is one record per limit label, persisted in notify.json so a restart
# neither repeats a toast nor forgets one was due.

function Get-LimitRank($Limit) {
    if ($Limit.shown -ge 100) { return 3 }
    switch ($Limit.level) { 'critical' { return 2 } 'warning' { return 1 } default { return 0 } }
}

function Get-Notifications($Snap, $State, [double]$Now) {
    # -> @{ events = @(@{ title; text; rank }); state = <new state> }. Pure, so
    # every rule below is a test case rather than a thing to wait for.
    $events = @(); $next = @{}
    if ($null -eq $Snap -or $Snap.error) {
        # Last-known numbers are not news; judge them when they are current.
        return @{ events = $events; state = $State }
    }
    foreach ($l in @($Snap.limits)) {
        $rank = Get-LimitRank $l
        $prev = if ($null -ne $State -and $State.ContainsKey($l.label)) { $State[$l.label] } else { $null }
        $cd = Format-Countdown $l.resets_at $Now
        $when = if ($cd -and $cd -ne 'now') { "Resets in $cd." } else { '' }
        # A new window shows as resets_at moving later. The endpoint stamps it
        # with sub-second jitter between fetches, hence the ten-minute slack.
        $rolled = $null -ne $prev -and $null -ne $prev.resets_at -and $null -ne $l.resets_at -and
                  ([double]$l.resets_at - [double]$prev.resets_at) -gt 600
        if ($rolled -and $prev.rank -ge 1 -and $rank -eq 0) {
            $events += , @{ rank = 0; title = "Claude $($l.label) limit has reset"
                            text = "Now at $($l.shown)%. " + $(if ($cd) { "Next reset in $cd." } else { '' }) }
        } elseif ($rank -gt $(if ($null -ne $prev -and -not $rolled) { $prev.rank } else { 0 })) {
            $title = if ($rank -eq 3) { "Claude $($l.label) limit reached" } else { "Claude $($l.label) limit at $($l.shown)%" }
            $events += , @{ rank = $rank; title = $title; text = $when }
        }
        # Always the current rank, falling as well as rising: a limit reset
        # early (resets_at unchanged) that climbs back up deserves its toast.
        $next[$l.label] = @{ rank = $rank; resets_at = $l.resets_at }
    }
    return @{ events = $events; state = $next }
}

function Merge-Notifications($Events) {
    # One toast per tick: a second ShowBalloonTip replaces the first, so two
    # limits crossing together would otherwise lose one. Most severe leads.
    $list = @($Events | Sort-Object { $_.rank } -Descending)
    if ($list.Count -eq 0) { return $null }
    $text = if ($list.Count -eq 1) { $list[0].text } else { (@($list | ForEach-Object { $_.title -replace '^Claude ', '' }) -join "`n") }
    return @{ title = $list[0].title; text = $text; warning = ($list[0].rank -ge 2) }
}

function ConvertFrom-NotifyState([string]$Json) {
    $state = @{}
    if (-not $Json) { return $state }
    $o = $Json | ConvertFrom-Json
    foreach ($p in $o.PSObject.Properties) {
        $r = Get-OptionalValue $p.Value 'resets_at'
        $state[$p.Name] = @{ rank = [int](Get-OptionalValue $p.Value 'rank' 0); resets_at = $(if ($null -ne $r) { [double]$r } else { $null }) }
    }
    return $state
}

# --- keeping the icon out of the overflow ----------------------------------------------
# Windows 11 parks a new tray icon in the overflow (^) and remembers each
# icon's placement under HKCU\Control Panel\NotifyIconSettings\<id>, where
# IsPromoted = 1 shows it on the taskbar - effective at once, no Explorer
# restart. Explorer writes our entry lazily (measured: not on add or remove;
# by the next sign-in), so the tray looks for it on every tick until it has
# decided. It is found by executable and the tooltip the icon was registered
# with, which is why the icon is first shown as plain "Claude usage".

$IconTooltip = 'Claude usage'

function Find-IconSetting($Entries, [string]$Tooltip) {
    @($Entries | Where-Object {
        "$($_.exe)" -like '*\WindowsPowerShell\v1.0\powershell.exe' -and "$($_.tip)" -eq $Tooltip
    }) | Select-Object -First 1
}

function Get-PromotionAction($Entry) {
    # 'wait' until Explorer has written the entry; 'promote' while nobody has
    # chosen; 'keep' once IsPromoted exists - whether we set it or the user
    # switched the icon off in Settings, that choice stands.
    if ($null -eq $Entry) { return 'wait' }
    if ($null -eq $Entry.promoted) { return 'promote' }
    return 'keep'
}

# --- naming the toasts -------------------------------------------------------------------
# Explorer turns a tray balloon into a toast sent under a synthetic app id,
# Microsoft.Explorer.Notification.{<hash of the exe and icon number>}, and
# without a registered name the toast header shows that id verbatim. A
# DisplayName (and IconUri) under HKCU\Software\Classes\AppUserModelId\<id>
# names it - Windows caches it, so it can take a toast or two to show. The id
# for the first NotifyIcon of 64-bit powershell.exe is known (measured; a
# hash of the path, so the same on any machine); anything else that carried
# one of our toasts is found afterwards by its LastNotificationAddedTime.

$ToastName = 'Claude usage'
$KnownToastIds = @('Microsoft.Explorer.Notification.{B0AA627D-AE34-F5C9-9971-19C8E1D372A3}')

function Select-ToastSenders($Entries, [long]$Since) {
    # Entries: @{ id; last } from ...\Notifications\Settings, `last` a FILETIME.
    @($Entries | Where-Object { $_.id -like 'Microsoft.Explorer.Notification.*' -and $null -ne $_.last -and [long]$_.last -ge $Since } |
      ForEach-Object { $_.id })
}

if ($Library) { return }

# --- offscreen render modes ----------------------------------------------------

$config = if (Test-Path $ConfigPath) { Get-Content -Raw $ConfigPath | ConvertFrom-Json } else { $null }
$theme = Get-Theme $config

if ($RenderPanel -or $RenderIcon) {
    $snap = if ($Snapshot) { ConvertFrom-Snapshot (Get-Content -Raw $Snapshot) } else { $null }
    $now = Get-NowEpoch
    if ($RenderPanel) {
        $fonts = New-Fonts 1.0
        $layout = Get-PanelLayout $snap $theme $fonts 1.0 $now $Idle.IsPresent ''
        $bmp = New-Object Drawing.Bitmap($layout.width, $layout.height)
        $g = [Drawing.Graphics]::FromImage($bmp)
        try { Invoke-PanelPaint $g $layout $theme } finally { $g.Dispose() }
        $bmp.Save($RenderPanel, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    }
    if ($RenderIcon) {
        $level = Get-IconLevel $snap $Idle.IsPresent ''
        $bmp = New-IconBitmap (Get-IconText $snap) (Get-LevelColor $theme $level) $theme.bg 64
        $bmp.Save($RenderIcon, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    }
    return
}

# --- the tray --------------------------------------------------------------------

if ($null -eq $config) { throw "no config at $ConfigPath - run windows/claude-usage/install.py from WSL" }
$Distro = [string]$config.distro
$Collector = @([string]$config.python, [string]$config.script, '--json')
$IntervalMs = 1000 * [int](Get-OptionalValue $config 'interval' 60)
$StateDir = Split-Path -Parent $ConfigPath
$LastPath = Join-Path $StateDir 'last.json'
$LogPath = Join-Path $StateDir 'tray.log'
$NotifyPath = Join-Path $StateDir 'notify.json'
$NotifyOn = [bool](Get-OptionalValue $config 'notify' $true)
$IconPngPath = Join-Path $StateDir 'icon.png'

$mutex = New-Object Threading.Mutex($false, 'Local\ClaudeUsageTray')
if (-not $mutex.WaitOne(0)) { return }   # one tray per session; install.py restarts it
# install.py sets this to stop the tray before replacing it. Exiting on a
# signal, rather than being killed, is what removes the icon: a killed
# process leaves a ghost in the notification area until the mouse passes it.
$exitEvent = New-Object Threading.EventWaitHandle($false, 'AutoReset', 'Local\ClaudeUsageTray.Exit')

function Write-TrayLog([string]$Message) {
    try {
        if ((Test-Path $LogPath) -and (Get-Item $LogPath).Length -gt 256KB) {
            Move-Item -Force $LogPath "$LogPath.1"
        }
        Add-Content -Path $LogPath -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message)
    } catch { }
}

Add-Type -Namespace ClaudeUsage -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr handle);
[DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
'@
[void][ClaudeUsage.Native]::SetProcessDPIAware()
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetUnhandledExceptionMode([Windows.Forms.UnhandledExceptionMode]::CatchException)
[Windows.Forms.Application]::add_ThreadException({ param($s, $e) Write-TrayLog "unhandled: $($e.Exception)" })

$script:snap = $null
$script:idle = $false
$script:fault = ''
$script:job = $null
$script:iconHandle = [IntPtr]::Zero
$script:hiddenAt = [datetime]::MinValue

$script:notifyState = @{}
if (Test-Path $NotifyPath) {
    try { $script:notifyState = ConvertFrom-NotifyState (Get-Content -Raw $NotifyPath) } catch { Write-TrayLog "notify.json: $_" }
}
$script:promotion = 'wait'
$script:toastCheckAt = $null; $script:toastSince = 0L

if (Test-Path $LastPath) {
    try { $script:snap = ConvertFrom-Snapshot (Get-Content -Raw $LastPath) } catch { Write-TrayLog "last.json: $_" }
}

$tray = New-Object Windows.Forms.NotifyIcon
$panel = New-Object Windows.Forms.Form
$panel.FormBorderStyle = 'None'; $panel.ShowInTaskbar = $false; $panel.TopMost = $true
$panel.StartPosition = 'Manual'; $panel.KeyPreview = $true
[Windows.Forms.Control].GetProperty('DoubleBuffered', [Reflection.BindingFlags]'NonPublic, Instance').SetValue($panel, $true)
$scale = $panel.CreateGraphics().DpiX / 96.0
$fonts = New-Fonts $scale
$script:layout = $null

function Update-Layout {
    $script:layout = Get-PanelLayout $script:snap $theme $fonts $scale (Get-NowEpoch) $script:idle $script:fault
    $panel.ClientSize = New-Object Drawing.Size($script:layout.width, $script:layout.height)
}

function Update-Tray {
    $now = Get-NowEpoch
    $size = [Windows.Forms.SystemInformation]::SmallIconSize.Width
    $level = Get-IconLevel $script:snap $script:idle $script:fault
    $bmp = New-IconBitmap (Get-IconText $script:snap) (Get-LevelColor $theme $level) $theme.bg $size
    $handle = $bmp.GetHicon(); $bmp.Dispose()
    $tray.Icon = [Drawing.Icon]::FromHandle($handle)
    if ($script:iconHandle -ne [IntPtr]::Zero) { [void][ClaudeUsage.Native]::DestroyIcon($script:iconHandle) }
    $script:iconHandle = $handle
    $tray.Text = Get-HoverText $script:snap $now $script:idle $script:fault
    if ($panel.Visible) { Update-Layout; Set-PanelPosition; $panel.Invalidate() }
}

function Set-PanelPosition {
    # Next to the icon, whichever edge the taskbar is on: the cursor is on the
    # icon when it is clicked, and the working area excludes the taskbar.
    $c = [Windows.Forms.Cursor]::Position
    $wa = [Windows.Forms.Screen]::FromPoint($c).WorkingArea
    $m = [int](8 * $scale); $w = $panel.Width; $h = $panel.Height
    $x = [Math]::Min([Math]::Max($c.X - [int]($w / 2), $wa.Left + $m), $wa.Right - $w - $m)
    if ($c.Y -ge $wa.Bottom) { $y = $wa.Bottom - $h - $m }
    elseif ($c.Y -lt $wa.Top) { $y = $wa.Top + $m }
    else {
        $y = [Math]::Min([Math]::Max($c.Y - [int]($h / 2), $wa.Top + $m), $wa.Bottom - $h - $m)
        $x = if ($c.X -ge $wa.Right) { $wa.Right - $w - $m } elseif ($c.X -lt $wa.Left) { $wa.Left + $m } else { $x }
    }
    $panel.Location = New-Object Drawing.Point($x, $y)
}

function Start-Collector([string[]]$Extra = @(), [switch]$Force) {
    if ($null -ne $script:job) { return }
    if (-not $Force) {
        # Never boot WSL from a timer: a tray that starts the VM every minute
        # also stops it from ever idling out. An explicit Refresh may.
        $script:idle = -not (Test-DistroRunning (Invoke-WslList) $Distro)
        if ($script:idle) { Update-Tray; return }
    }
    $psi = New-Object Diagnostics.ProcessStartInfo('wsl.exe')
    $psi.Arguments = ConvertTo-ArgumentString (@('-d', $Distro, '--exec') + $Collector + $Extra)
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8; $psi.StandardErrorEncoding = [Text.Encoding]::UTF8
    try {
        $p = [Diagnostics.Process]::Start($psi)
        $script:job = @{ proc = $p; out = $p.StandardOutput.ReadToEndAsync(); err = $p.StandardError.ReadToEndAsync(); started = Get-Date }
    } catch {
        $script:fault = "could not start wsl.exe: $($_.Exception.Message)"; Write-TrayLog $script:fault; Update-Tray
    }
}

function Invoke-WslList {
    $psi = New-Object Diagnostics.ProcessStartInfo('wsl.exe', '--list --running --quiet')
    $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true; $psi.RedirectStandardOutput = $true
    $psi.EnvironmentVariables['WSL_UTF8'] = '1'
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    try {
        $p = [Diagnostics.Process]::Start($psi)
        $out = $p.StandardOutput.ReadToEnd()
        if (-not $p.WaitForExit(10000)) { $p.Kill() }
        return $out -split "`r?`n"
    } catch { Write-TrayLog "wsl --list: $_"; return @() }
}

function Complete-Collector {
    $j = $script:job
    if ($null -eq $j) { return }
    if (-not ($j.proc.HasExited -and $j.out.IsCompleted -and $j.err.IsCompleted)) {
        # The first run after a cache wipe rescans every transcript; give it
        # two minutes before deciding it hung.
        if (((Get-Date) - $j.started).TotalSeconds -gt 120) {
            try { $j.proc.Kill() } catch { }
            $script:job = $null
            $script:fault = 'collector timed out after 120s'; Write-TrayLog $script:fault; Update-Tray
        }
        return
    }
    $script:job = $null
    $stderr = $j.err.Result.Trim()
    if ($stderr) { Write-TrayLog "collector stderr: $stderr" }
    try {
        if ($j.proc.ExitCode -ne 0) {
            $first = ($stderr -split "`n" | Where-Object { $_ } | Select-Object -Last 1)
            throw "collector exited $($j.proc.ExitCode)$(if ($first) { ": $first" })"
        }
        $json = $j.out.Result
        $script:snap = ConvertFrom-Snapshot $json
        $script:fault = ''; $script:idle = $false
        Write-Utf8 $LastPath $json
        try { Invoke-Notifications } catch { Write-TrayLog "notify: $_" }
    } catch {
        $script:fault = "$($_.Exception.Message)"
        if ($script:fault.Length -gt 120) { $script:fault = $script:fault.Substring(0, 119) + [char]0x2026 }
        Write-TrayLog "collector: $($_.Exception.Message)"
    }
    Update-Tray
}

function Write-Utf8([string]$Path, [string]$Text) {
    # Without a BOM: 5.1's `Set-Content -Encoding UTF8` writes one, and these
    # files are read by more than this script (python, jq, editors).
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

function Register-ToastSender([string]$Id) {
    $k = "HKCU:\Software\Classes\AppUserModelId\$Id"
    if ((Test-Path $k) -and (Get-OptionalValue (Get-ItemProperty $k) 'DisplayName') -eq $ToastName) { return }
    New-Item -Force -Path $k | Out-Null
    Set-ItemProperty -Path $k -Name DisplayName -Value $ToastName
    if (Test-Path $IconPngPath) { Set-ItemProperty -Path $k -Name IconUri -Value $IconPngPath }
    Write-TrayLog "named toast sender $Id"
}

function Show-Toast([string]$Title, [string]$Text, [Windows.Forms.ToolTipIcon]$Kind) {
    $tray.ShowBalloonTip(10000, $Title, $(if ($Text) { $Text } else { ' ' }), $Kind)
    # Look for the sender a few seconds on, once Explorer has stamped it.
    $script:toastSince = [DateTime]::UtcNow.AddSeconds(-2).ToFileTimeUtc()
    $script:toastCheckAt = (Get-Date).AddSeconds(5)
}

function Find-ToastSender {
    if ($null -eq $script:toastCheckAt -or (Get-Date) -lt $script:toastCheckAt) { return }
    $script:toastCheckAt = $null
    $root = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings'
    $entries = @(Get-ChildItem $root -ErrorAction SilentlyContinue | ForEach-Object {
        @{ id = $_.PSChildName; last = $_.GetValue('LastNotificationAddedTime') } })
    foreach ($id in Select-ToastSenders $entries $script:toastSince) { Register-ToastSender $id }
}

function Invoke-Notifications {
    if (-not $NotifyOn) { return }
    $r = Get-Notifications $script:snap $script:notifyState (Get-NowEpoch)
    $toast = Merge-Notifications $r.events
    if ($null -ne $toast) {
        $kind = if ($toast.warning) { [Windows.Forms.ToolTipIcon]::Warning } else { [Windows.Forms.ToolTipIcon]::Info }
        Show-Toast $toast.title $toast.text $kind
        Write-TrayLog "notified: $($toast.title)"
    }
    $script:notifyState = $r.state
    Write-Utf8 $NotifyPath ($r.state | ConvertTo-Json -Depth 4 -Compress)
}

function Invoke-IconPromotion {
    if ($script:promotion -ne 'wait') { return }
    $root = 'HKCU:\Control Panel\NotifyIconSettings'
    if (-not (Test-Path $root)) { return }
    $entries = @(Get-ChildItem $root | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath
        @{ path = $_.PSPath; exe = (Get-OptionalValue $p 'ExecutablePath' '');
           tip = (Get-OptionalValue $p 'InitialTooltip' ''); promoted = (Get-OptionalValue $p 'IsPromoted') }
    })
    $entry = Find-IconSetting $entries $IconTooltip
    $script:promotion = Get-PromotionAction $entry
    if ($script:promotion -eq 'promote') {
        Set-ItemProperty -Path $entry.path -Name IsPromoted -Value 1 -Type DWord
        $script:promotion = 'keep'
        Write-TrayLog 'icon moved out of the overflow onto the taskbar (IsPromoted=1)'
    }
}

function Show-Panel {
    Update-Layout; Set-PanelPosition
    $panel.Show(); $panel.Activate()
}

$panel.add_Paint({ param($s, $e)
    try { if ($null -ne $script:layout) { Invoke-PanelPaint $e.Graphics $script:layout $theme } } catch { Write-TrayLog "paint: $_" } })
$panel.add_Deactivate({ $panel.Hide(); $script:hiddenAt = Get-Date })
$panel.add_KeyDown({ param($s, $e) if ($e.KeyCode -eq 'Escape') { $panel.Hide() } })
$panel.add_HandleCreated({
    # Windows 11 rounded corners (DWMWA_WINDOW_CORNER_PREFERENCE = 33,
    # DWMWCP_ROUND = 2); a no-op returning an error on Windows 10.
    $round = 2; [void][ClaudeUsage.Native]::DwmSetWindowAttribute($panel.Handle, 33, [ref]$round, 4) })

$tray.add_MouseClick({ param($s, $e)
    try {
        if ($e.Button -ne 'Left') { return }
        # Clicking the icon while the panel is open deactivates the panel
        # first, so "toggle" would reopen it at once; a click straight after
        # that hide is the closing click.
        if ($panel.Visible) { $panel.Hide(); return }
        if (((Get-Date) - $script:hiddenAt).TotalMilliseconds -lt 400) { return }
        Show-Panel
        Start-Collector
    } catch { Write-TrayLog "click: $_" } })

$menu = New-Object Windows.Forms.ContextMenuStrip
[void]$menu.Items.Add('Refresh now', $null, { try { Start-Collector @('--refresh') -Force } catch { Write-TrayLog "refresh: $_" } })
[void]$menu.Items.Add('Limits were reset early...', $null, {
    try {
        $answer = [Windows.Forms.MessageBox]::Show(
            "Use this when Anthropic resets your limits ahead of schedule. The pace markers will measure from now until each limit's normal reset. The token charts are not affected.`n`nUndo by deleting ~/.local/state/claude-usage/limits-reset-at in WSL.",
            'Claude usage', 'OKCancel', 'Information')
        if ($answer -eq 'OK') { Start-Collector @('--limits-reset') -Force }
    } catch { Write-TrayLog "reset: $_" } })
[void]$menu.Items.Add('Open usage page', $null, { Start-Process $UsageUrl })
[void]$menu.Items.Add('Send test notification', $null, {
    Show-Toast 'Claude usage' 'Notifications are working. Limits notify at 70%, 90% and 100%, and again when they reset.' ([Windows.Forms.ToolTipIcon]::Info) })
[void]$menu.Items.Add('Open log', $null, { if (Test-Path $LogPath) { Start-Process notepad.exe $LogPath } })
[void]$menu.Items.Add('-')
[void]$menu.Items.Add('Exit', $null, { $tray.Visible = $false; [Windows.Forms.Application]::Exit() })
$tray.ContextMenuStrip = $menu

$poll = New-Object Windows.Forms.Timer; $poll.Interval = 250
$poll.add_Tick({
    try {
        if ($exitEvent.WaitOne(0)) { $tray.Visible = $false; [Windows.Forms.Application]::Exit(); return }
        Complete-Collector
        Find-ToastSender
    } catch { Write-TrayLog "poll: $_" } })
$tick = New-Object Windows.Forms.Timer; $tick.Interval = $IntervalMs
$tick.add_Tick({
    try { Start-Collector } catch { Write-TrayLog "tick: $_" }
    try { Invoke-IconPromotion } catch { Write-TrayLog "promote: $_"; $script:promotion = 'keep' } })
$tray.add_BalloonTipClicked({ try { Show-Panel } catch { Write-TrayLog "toast click: $_" } })

try {
    # The toasts' icon: the tray tile, carrying a percent sign.
    $png = New-IconBitmap '%' $theme.accent $theme.bg 64
    $png.Save($IconPngPath, [Drawing.Imaging.ImageFormat]::Png); $png.Dispose()
    foreach ($id in $KnownToastIds) { Register-ToastSender $id }
} catch { Write-TrayLog "toast name: $_" }
Update-Tray
# Registered under a fixed tooltip, then given the live one: the fixed text is
# what Explorer records as InitialTooltip, and what Invoke-IconPromotion finds.
$tray.Text = $IconTooltip
$tray.Visible = $true
$tray.Text = Get-HoverText $script:snap (Get-NowEpoch) $script:idle $script:fault
try { Invoke-IconPromotion } catch { Write-TrayLog "promote: $_"; $script:promotion = 'keep' }
$poll.Start(); $tick.Start()
Start-Collector
Write-TrayLog "started: distro=$Distro interval=$($IntervalMs / 1000)s notify=$NotifyOn icon=$script:promotion"
try {
    [Windows.Forms.Application]::Run()
} finally {
    $tray.Visible = $false; $tray.Dispose()
    if ($script:iconHandle -ne [IntPtr]::Zero) { [void][ClaudeUsage.Native]::DestroyIcon($script:iconHandle) }
    $mutex.ReleaseMutex(); $mutex.Dispose(); $exitEvent.Dispose()
    Write-TrayLog 'stopped'
}
