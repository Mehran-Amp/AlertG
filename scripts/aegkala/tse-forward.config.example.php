<?php
// Copy to tse-forward.config.php on the host (same folder as tse-forward.php) and edit. NEVER commit the real one.
return [
    'token'     => 'CHANGE-ME-random-letters-and-digits-at-least-24-chars',
    'allow_ips' => ['5.9.73.60'],   // server360's public IP; [] = no IP restriction (token only)
];
