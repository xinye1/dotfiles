<#
Tests for windows/claude-usage/ClaudeUsageTray.ps1 (PLAYBOOK §9.31).

Run by tests/claude_tray_test.py, which writes the fixtures with the real
claude_usage.snapshot() — so a change to the snapshot's shape fails here, at
the boundary, instead of on the Windows desktop. Windows PowerShell 5.1 only
(System.Windows.Forms); no Pester, which 5.1 ships in a version too old to
share syntax with anything current.

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File claude_tray_test.ps1 -FixtureDir <dir> -Now <epoch>
#>
param(
    [Parameter(Mandatory)][string]$FixtureDir,
    [Parameter(Mandatory)][double]$Now
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\windows\claude-usage\ClaudeUsageTray.ps1') -Library
Set-StrictMode -Version 2.0

$script:failed = 0; $script:passed = 0
function Check([string]$Name, [scriptblock]$Body) {
    try {
        $r = & $Body
        if ($r -ne $true) { throw "returned $r" }
        $script:passed++
    } catch {
        $script:failed++
        Write-Output "FAIL $Name : $($_.Exception.Message)"
    }
}
function Eq($Got, $Want) {
    if ($Got -ne $Want) { throw "got [$Got], want [$Want]" }
    return $true
}
function Fixture([string]$Name) { ConvertFrom-Snapshot (Get-Content -Raw (Join-Path $FixtureDir $Name)) }

$full = Fixture 'full.json'
$stale = Fixture 'stale.json'
$empty = Fixture 'empty.json'

# --- countdown: claude_usage.countdown()'s format, from epochs ---------------
Check 'countdown hours' { Eq (Format-Countdown ($Now + 3 * 3600 + 13 * 60) $Now) '3h 13m' }
Check 'countdown days' { Eq (Format-Countdown ($Now + 4 * 86400 + 22 * 3600) $Now) '4d 22h' }
Check 'countdown minutes' { Eq (Format-Countdown ($Now + 5 * 60) $Now) '5m' }
Check 'countdown past is now' { Eq (Format-Countdown ($Now - 3600) $Now) 'now' }
Check 'countdown none' { Eq (Format-Countdown $null $Now) '' }
Check 'countdown matches python on the fixture' {
    # full.json's session resets 3h 13m after the fixture's NOW.
    Eq (Format-Countdown $full.limits[0].resets_at $Now) '3h 13m'
}

# --- pace -------------------------------------------------------------------------
Check 'pace from the snapshot window' {
    # Session: 5h window ending 3h13m from now -> 1h47m in = 0.3567.
    $f = Get-PaceFraction $full.limits[0] $Now
    [Math]::Abs($f - (107 / 300)) -lt 1e-6
}
Check 'pace clamps both ends' {
    $l = @{ window_start = $Now; resets_at = $Now + 100 }
    (Eq (Get-PaceFraction $l ($Now - 50)) 0.0) -and (Eq (Get-PaceFraction $l ($Now + 500)) 1.0)
}
Check 'pace null without a window' {
    $null -eq (Get-PaceFraction @{ window_start = $null; resets_at = $Now } $Now)
}
Check 'pace null for a zero-length window' {
    $null -eq (Get-PaceFraction @{ window_start = $Now; resets_at = $Now } $Now)
}

# --- snapshot parsing ---------------------------------------------------------------
Check 'parse keeps python decisions' {
    (Eq (($full.limits | ForEach-Object { $_.label }) -join ',') 'Session,Weekly,Fable Wk') -and
    (Eq (($full.limits | ForEach-Object { $_.shown }) -join ',') '44,41,70') -and
    (Eq $full.limits[2].level 'warning') -and (Eq $full.level 'warning') -and (Eq $full.tier 'Max')
}
Check 'parse days and models' {
    (Eq @($full.days).Count 7) -and (Eq $full.days[6].date '2026-08-22') -and
    (Eq $full.days[6].human '57.7M') -and (Eq $full.models[0].name 'Opus 5')
}
Check 'parse stale' { (Eq $stale.error 'HTTP 429') -and (Eq $stale.level 'stale') -and (Eq @($stale.days).Count 0) -and (Eq $stale.retry_at ($Now + 600)) }
Check 'parse never-logged-in' { (Eq @($empty.limits).Count 0) -and ($null -eq $empty.fetched_at) }
Check 'unknown schema refused' {
    try { [void](Fixture 'bad_schema.json'); $false } catch { $_.Exception.Message -like '*schema 99*' }
}
Check 'missing optional fields default' {
    $s = ConvertFrom-Snapshot '{"schema": 1, "limits": [{"label": "X"}]}'
    (Eq $s.limits[0].shown 0) -and ($null -eq $s.limits[0].resets_at) -and (Eq @($s.days).Count 0)
}

# --- hover text -----------------------------------------------------------------------
Check 'hover fits and carries countdowns when there is room' {
    $t = Get-HoverText $full $Now $false ''
    ($t.Length -le 63) -and ($t -like "Session 44% $([char]0x00B7) 3h 13m*") -and ($t.Split("`n").Count -eq 3)
}
Check 'hover sheds countdowns before the status' {
    $t = Get-HoverText $stale $Now $false ''
    ($t.Length -le 63) -and ($t -like '*stale: HTTP 429') -and ($t -notlike "*$([char]0x00B7)*")
}
Check 'hover never exceeds the NotifyIcon limit' {
    $many = @{ limits = @(1..8 | ForEach-Object { @{ label = "Very Long Limit Label $_"; shown = 99; resets_at = $Now + 86400 } })
               error = 'network error'; level = 'stale'; generated_at = $Now }
    $ok = $true
    foreach ($fault in '', ('x' * 200)) {
        foreach ($idle in $true, $false) {
            if ((Get-HoverText $many $Now $idle $fault).Length -gt 63) { $ok = $false }
        }
    }
    $ok
}
Check 'hover with nothing yet' { Eq (Get-HoverText $null $Now $true '') 'Claude usage: WSL idle, no data yet' }
Check 'hover says idle' { (Get-HoverText $full $Now $true '') -like '*WSL idle since*' }
Check 'hover says fault first' { (Get-HoverText $full $Now $true 'collector exited 1') -like '*error: collector exited 1' }

# --- icon -----------------------------------------------------------------------------
Check 'icon text is the worst percent' { Eq (Get-IconText $full) '70' }
Check 'icon text without limits' { Eq (Get-IconText $empty) ([string][char]0x2013) }
Check 'icon level' {
    (Eq (Get-IconLevel $full $false '') 'warning') -and (Eq (Get-IconLevel $full $true '') 'stale') -and
    (Eq (Get-IconLevel $full $false 'boom') 'stale') -and (Eq (Get-IconLevel $stale $false '') 'stale') -and
    (Eq (Get-IconLevel $null $false '') 'stale')
}
Check 'icon bitmap fits three digits at 16px' {
    $b = New-IconBitmap '100' ([Drawing.Color]::Orange) ([Drawing.Color]::Black) 16
    try { Eq $b.Width 16 } finally { $b.Dispose() }
}

# --- wsl plumbing -------------------------------------------------------------------------
Check 'distro running: exact, case-insensitive' {
    (Test-DistroRunning @('Ubuntu', '') 'ubuntu') -and -not (Test-DistroRunning @('Ubuntu-24.04') 'Ubuntu') -and
    -not (Test-DistroRunning @('There are no running distributions.') 'Ubuntu') -and
    (Test-DistroRunning @("Debian`r", "Ubuntu$([char]0)") 'Ubuntu')
}
Check 'argument quoting' {
    Eq (ConvertTo-ArgumentString @('-d', 'Ubuntu', '--exec', '/home/a b/c.py', 'x"y', 'C:\dir\', '')) `
        '-d Ubuntu --exec "/home/a b/c.py" "x\"y" C:\dir\ ""'
}
Check 'argument quoting doubles a trailing backslash inside quotes' {
    Eq (ConvertTo-ArgumentString @('C:\a b\')) '"C:\a b\\"'
}

# --- theme --------------------------------------------------------------------------------
Check 'theme from config, fallback for the rest, junk ignored' {
    $cfg = '{"theme": {"bg": "' + [char]35 + '2e3440", "fg": "not-a-colour"}}' | ConvertFrom-Json
    $t = Get-Theme $cfg
    (Eq $t.bg.R 0x2e) -and (Eq $t.fg.Name 'White') -and (Eq $t.indicator.Name 'LightGreen')
}
Check 'theme without config' { (Get-Theme $null).critical.Name -eq 'Tomato' }
Check 'day label' {
    $today = [datetime]'2026-08-22'
    (Eq (Get-DayLabel '2026-08-22' $today) 'Today') -and (Eq (Get-DayLabel '2026-08-21' $today) 'Fri')
}

# --- notifications --------------------------------------------------------------------------
function Snap([object[]]$Rows, $Err = $null) {
    @{ error = $Err; limits = @($Rows | ForEach-Object {
        @{ label = $_[0]; shown = $_[1]; level = $(if ($_[1] -ge 90) { 'critical' } elseif ($_[1] -ge 70) { 'warning' } else { 'normal' }); resets_at = $_[2] } }) }
}
$Reset = $Now + 3 * 3600   # not $Reset: PowerShell names are case-insensitive, and $r is taken
Check 'no toast on first sight below the bands' {
    $r = Get-Notifications (Snap @(, @('Session', 40, $Reset))) @{} $Now
    (Eq @($r.events).Count 0) -and (Eq $r.state['Session'].rank 0)
}
Check 'first sight inside a band toasts once' {
    $r = Get-Notifications (Snap @(, @('Weekly', 75, $Reset))) @{} $Now
    (Eq @($r.events).Count 1) -and (Eq $r.events[0].title 'Claude Weekly limit at 75%') -and (Eq $r.events[0].text 'Resets in 3h 0m.')
}
Check 'each band toasts on the way up, once' {
    $st = @{}; $seen = @()
    foreach ($pct in 50, 69, 70, 74, 89, 90, 95, 100, 100) {
        $r = Get-Notifications (Snap @(, @('Session', $pct, $Reset))) $st $Now
        $seen += @($r.events | ForEach-Object { $_.rank }); $st = $r.state
    }
    Eq ($seen -join ',') '1,2,3'
}
Check '100% says reached' {
    $r = Get-Notifications (Snap @(, @('Session', 100, $Reset))) @{ Session = @{ rank = 2; resets_at = $Reset } } $Now
    Eq $r.events[0].title 'Claude Session limit reached'
}
Check 'a window rolling over after a band toasts the reset' {
    $st = @{ Session = @{ rank = 2; resets_at = $Reset } }
    $r = Get-Notifications (Snap @(, @('Session', 0, ($Reset + 5 * 3600)))) $st $Now
    (Eq @($r.events).Count 1) -and (Eq $r.events[0].title 'Claude Session limit has reset') -and
    ($r.events[0].text -like 'Now at 0%. Next reset in*')
}
Check 'a quiet window rolling over is not news' {
    $r = Get-Notifications (Snap @(, @('Session', 0, ($Reset + 5 * 3600)))) @{ Session = @{ rank = 0; resets_at = $Reset } } $Now
    Eq @($r.events).Count 0
}
Check 'resets_at jitter is not a new window' {
    $st = @{ Session = @{ rank = 1; resets_at = $Reset } }
    $r = Get-Notifications (Snap @(, @('Session', 72, ($Reset + 0.03)))) $st $Now
    Eq @($r.events).Count 0
}
Check 'an early reset re-arms the band' {
    # Same resets_at, percent falls (Anthropic reset early), then climbs back.
    $st = @{ Weekly = @{ rank = 1; resets_at = $Reset } }
    $a = Get-Notifications (Snap @(, @('Weekly', 5, $Reset))) $st $Now
    $b = Get-Notifications (Snap @(, @('Weekly', 71, $Reset))) $a.state $Now
    (Eq @($a.events).Count 0) -and (Eq @($b.events).Count 1)
}
Check 'stale data changes nothing' {
    $st = @{ Session = @{ rank = 0; resets_at = $Reset } }
    $r = Get-Notifications (Snap @(, @('Session', 95, $Reset)) 'HTTP 429') $st $Now
    (Eq @($r.events).Count 0) -and (Eq $r.state['Session'].rank 0)
}
Check 'limits that disappear drop out of the state' {
    $r = Get-Notifications (Snap @(, @('Session', 10, $Reset))) @{ Gone = @{ rank = 2; resets_at = $Reset } } $Now
    -not $r.state.ContainsKey('Gone')
}
Check 'two crossings merge into one toast, worst first' {
    $r = Get-Notifications (Snap @(@('Weekly', 71, $Reset), @('Session', 92, $Reset))) @{} $Now   # worst listed second
    $t = Merge-Notifications $r.events
    (Eq $t.title 'Claude Session limit at 92%') -and $t.warning -and (Eq $t.text "Session limit at 92%`nWeekly limit at 71%")
}
Check 'nothing to merge' { $null -eq (Merge-Notifications @()) }
Check 'state round-trips through notify.json' {
    $st = @{ Session = @{ rank = 2; resets_at = $Reset }; Weekly = @{ rank = 0; resets_at = $null } }
    $back = ConvertFrom-NotifyState ($st | ConvertTo-Json -Depth 4 -Compress)
    (Eq $back['Session'].rank 2) -and (Eq $back['Session'].resets_at $Reset) -and ($null -eq $back['Weekly'].resets_at) -and
    (Eq (ConvertFrom-NotifyState '').Count 0)
}

# --- icon promotion ---------------------------------------------------------------------------
$ps = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
Check 'finds only our icon: powershell plus the registration tooltip' {
    $entries = @(
        @{ exe = $ps; tip = 'Some other script'; promoted = $null },
        @{ exe = 'C:\x\other.exe'; tip = 'Claude usage'; promoted = $null },
        @{ exe = $ps; tip = 'Claude usage'; promoted = $null; path = 'ours' })
    Eq (Find-IconSetting $entries 'Claude usage').path 'ours'
}
Check 'promotion: wait, promote, then respect any choice' {
    (Eq (Get-PromotionAction $null) 'wait') -and
    (Eq (Get-PromotionAction @{ promoted = $null }) 'promote') -and
    (Eq (Get-PromotionAction @{ promoted = 0 }) 'keep') -and
    (Eq (Get-PromotionAction @{ promoted = 1 }) 'keep')
}

Check 'toast senders: explorer ids stamped since the toast, nothing else' {
    $since = 1000L
    $entries = @(
        @{ id = 'Microsoft.Explorer.Notification.{A}'; last = 1500L },
        @{ id = 'Microsoft.Explorer.Notification.{B}'; last = 500L },
        @{ id = 'Microsoft.Explorer.Notification.{C}'; last = $null },
        @{ id = 'Microsoft.Teams'; last = 2000L })
    Eq ((Select-ToastSenders $entries $since) -join ',') 'Microsoft.Explorer.Notification.{A}'
}

Check 'no top-level statement calls a function defined further down' {
    # PowerShell defines a function when execution reaches it, so a call
    # above its definition fails at runtime only - in the tray's startup,
    # which nothing else here runs. Calls inside scriptblock literals (event
    # handlers, timers) run later and are exempt; everything else counts.
    $path = Join-Path $PSScriptRoot '..\windows\claude-usage\ClaudeUsageTray.ps1'
    # .ProviderPath: under \\wsl.localhost, Resolve-Path's string form is
    # provider-qualified, ParseFile cannot open it, and with the errors
    # discarded this check once passed over an empty script. Hence both guards.
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path).ProviderPath, [ref]$null, [ref]$errors)
    if (@($errors).Count -gt 0) { throw "parse errors: $($errors[0])" }
    if ($ast.EndBlock.Statements.Count -lt 50) { throw "only $($ast.EndBlock.Statements.Count) statements parsed" }
    $all = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | ForEach-Object { $_.Name })
    $defined = @{}; $bad = @()
    foreach ($st in $ast.EndBlock.Statements) {
        if ($st -is [Management.Automation.Language.FunctionDefinitionAst]) { $defined[$st.Name] = $true; continue }
        $calls = $st.FindAll({ param($n)
            if (-not ($n -is [Management.Automation.Language.CommandAst])) { return $false }
            for ($q = $n.Parent; $null -ne $q; $q = $q.Parent) {
                if ($q -is [Management.Automation.Language.ScriptBlockExpressionAst] -or
                    $q -is [Management.Automation.Language.FunctionDefinitionAst]) { return $false }
            }
            return $true }, $true)
        foreach ($c in $calls) {
            $name = $c.GetCommandName()
            if ($name -and $all -contains $name -and -not $defined.ContainsKey($name)) { $bad += "$name (line $($c.Extent.StartLineNumber))" }
        }
    }
    if ($bad) { throw "called before defined: $($bad -join ', ')" }
    $true
}

# --- layout and paint ---------------------------------------------------------------------------
$theme = Get-Theme $null
$fonts = New-Fonts 1.0
function Paint($Snap, [bool]$Idle, [string]$Fault, [double]$Scale = 1.0) {
    $f = New-Fonts $Scale
    $l = Get-PanelLayout $Snap $theme $f $Scale $Now $Idle $Fault
    $bmp = New-Object Drawing.Bitmap($l.width, $l.height)
    $g = [Drawing.Graphics]::FromImage($bmp)
    try { Invoke-PanelPaint $g $l $theme } finally { $g.Dispose(); $bmp.Dispose() }
    return $l
}
function Texts($Layout) { @($Layout.ops | Where-Object { $_.kind -eq 'text' } | ForEach-Object { $_.text }) }
function Inside($Layout) {
    foreach ($op in $Layout.ops) {
        $right = if ($op.kind -eq 'rect') { $op.x + $op.w } elseif ($op.right) { $op.right } else { $op.x + (Measure-Width $op.text $op.font) }
        if ($op.x -lt 0 -or $right -gt $Layout.width) { throw "op '$($op.kind) $($op['text'])' spans $($op.x)..$right of $($Layout.width)" }
    }
    return $true
}

Check 'full panel paints, with every section, inside its bounds' {
    $l = Paint $full $false ''
    $t = Texts $l
    ($t -contains 'LIMITS') -and ($t -contains 'TOKENS BY DAY') -and ($t -contains 'TOKENS BY MODEL (7d)') -and
    ($t -contains 'resets in 3h 13m') -and ($t -contains '70%') -and ($t -contains 'Today') -and (Inside $l)
}
Check 'one pace marker per limit with a window, plus the legend' {
    $l = Get-PanelLayout $full $theme $fonts 1.0 $Now $false ''
    $markers = @($l.ops | Where-Object { $_.kind -eq 'rect' -and $_.color -eq $theme.fg_bright })
    Eq $markers.Count 4   # three bars + the legend's swatch
}
Check 'no marker, no legend, when no window is known' {
    $s = ConvertFrom-Snapshot '{"schema": 1, "level": "normal", "limits": [{"label": "X", "shown": 5, "fill": 0.05}]}'
    $l = Get-PanelLayout $s $theme $fonts 1.0 $Now $false ''
    -not ((Texts $l) | Where-Object { $_ -like 'now*' })
}
Check 'stale panel shows the banner and no charts' {
    $l = Paint $stale $false ''
    $t = Texts $l
    (@($t | Where-Object { $_ -like '*stale*HTTP 429*' }).Count -eq 1) -and ($t -notcontains 'TOKENS BY DAY') -and (Inside $l)
}
Check 'stale banner names the next try, until it has passed' {
    $want = "*HTTP 429, data from $(Format-Clock $stale.fetched_at), retry $(Format-Clock $stale.retry_at)"
    $now_ = @(Texts (Paint $stale $false '') | Where-Object { $_ -like $want }).Count -eq 1
    $late = Get-PanelLayout $stale $theme $fonts 1.0 ($Now + 601) $false ''
    $now_ -and -not (Texts $late | Where-Object { $_ -like '*retry*' })
}
Check 'idle with no data says how to start it' {
    $l = Paint $null $true ''
    @(Texts $l | Where-Object { $_ -like 'WSL is not running*Refresh now*' }).Count -eq 1
}
Check 'fault banner widens the panel rather than overflowing' {
    $l = Paint $full $false ('collector exited 1: ' + ('y' * 100))
    Inside $l
}
Check 'scales with DPI' {
    $a = Get-PanelLayout $full $theme (New-Fonts 1.0) 1.0 $Now $false ''
    $b = Get-PanelLayout $full $theme (New-Fonts 1.0) 2.0 $Now $false ''
    $b.width -gt $a.width + 100   # paddings and the bar double; text is in points
}
Check 'empty panel paints' { $l = Paint $empty $false ''; Inside $l }

Write-Output "claude_tray_test.ps1: $script:passed passed, $script:failed failed"
exit [int]($script:failed -gt 0)
