# Copy this file to bourse.config.ps1 (same folder) and fill in the values. bourse.config.ps1 is git-ignored.
# NO secrets in this file: keys live in separate files that you create on the PC.

# ---- Gateway (tsetmc-gateway) ----
$GatewayDir      = 'C:\tsetmc-gateway'                 # folder the gateway starts in
$GatewayExe      = 'python'                            # program to run (python, or a full path to an .exe)
$GatewayArgs     = 'tsetmc_gateway.py'                 # its arguments: the REAL script name in the gateway folder (-Check verifies the file exists)
$GatewayPort     = 8099
# Extra environment variables for the gateway process, for example the variable that sets its listen port.
# The gateway listens on 8080 unless told otherwise, but the tunnel and the server expect $GatewayPort.
# Use the REAL variable name from the gateway's README / .env.example, e.g.  @{ SOME_PORT_VARIABLE = '8099' }
$GatewayEnv      = @{ }

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
