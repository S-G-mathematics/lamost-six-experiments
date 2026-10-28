# Portable engineering qualification 717

The recorded portable engineering bundle passed 717 tests on EC2. Fingerprint 0ed0e338773c07faaa432ca78caf298fece068cac6457b800743be62bdb69575; bundle SHA-256 e883ff20b254bc029765237864d7c29bc890e5b706762a32efa9b9180add9f48.

This is software and fixture validation, not scientific evaluation or final archive verification. E4/E5 remain incomplete; frozen E1/E2 are unchanged.

A small launch wrapper is included at code/launch/run_cold_auto_compaction_717.sh (SHA-256 d99333330e30c6c85251cd9336d96651e8bedb78bca55bbbb520bcc64964ca78). It sets the runtime working directory before invoking the qualified source CLI. This fixes launch context only; it does not claim observed archive/fit overlap or a production cache hit.
