<?php
// Copy to tse-probe.config.php on the host (same folder as tse-probe.php) and edit. NEVER commit the real one.
return [
    'token'     => 'CHANGE-ME-to-a-random-string-of-at-least-16-characters',
    'allow_ips' => [],   // optional: ['<server360 public IP>'] - when set, only these callers are accepted
];
