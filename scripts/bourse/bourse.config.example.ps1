# Copy this file to bourse.config.ps1 (same folder) and fill in the values. bourse.config.ps1 is git-ignored.
# NO secrets in this file: keys live in separate files that you create on the PC.

# ---- Gateway (tsetmc-gateway) ----
$GatewayDir      = 'C:\tsetmc-gateway'                 # folder the gateway starts in
$GatewayExe      = 'python'                            # program to run (python, or a full path to an .exe)
$GatewayArgs     = 'tsetmc_gateway.py'                 # its arguments (adjust to how you start it today)
$GatewayPort     = 8099
$ApiKeyFile      = 'C:\tsetmc-gateway\api_key.txt'     # one line: the gateway key (= TSETMC_API_KEY); never commit it

# ---- SSH reverse tunnel to server360 ----
$SshHost         = 'server360.example.com'             # server address
$SshUser         = 'aisocial'                          # user on the server
$SshPort         = 22
$SshKeyFile      = "$env:USERPROFILE\.ssh\id_ed25519"  # private key for key-based login (the tunnel cannot type a password)
$RemotePort      = 8099                                # port opened on the server (server uses http://127.0.0.1:8099)

# ---- Behaviour ----
$LogDir          = "$PSScriptRoot\logs"
$CheckSeconds    = 20                                  # how often the supervisor looks at both processes
$HealthFailures  = 3                                   # consecutive failed health checks before the gateway is restarted
$MaxBackoff      = 120                                 # longest wait (seconds) between restarts
