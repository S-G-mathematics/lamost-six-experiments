# E6 primary ensemble availability finding

Observed UTC: 2026-10-25T16:15:22.155371+00:00

All six planned primary ensemble outcomes (equal and globally learned weights in each of three repetitions) are recorded as unavailable dependencies. None has an ensemble attempt. Each repetition has a required KDE direct member evaluation that terminated at the fixed 600-second evaluation limit in E3. The selected KDE generator fitting and synthetic generation succeeded; this finding concerns the direct member evaluation, not a failed generator fit or unavailable historical model.

The recorded E6 implementation amendment requires five validated selected fits and all five declared matching member evaluations before any tuning-posterior, calibration, or test computation. The immutable 6,270-task plan, original freeze time, scientific weight search, and resource limits were preserved by that amendment before any E6 ensemble evaluation. The gate prevents an implicit retry of the same unavailable comparison.

No tuning weight vector, ensemble balanced accuracy, ensemble coverage, or ensemble set-size result exists. No ensemble-versus-member benefit or lack of benefit can be inferred. No partial-member sensitivity analysis is added. E6 still has member-reference tasks pending; this is an availability finding for the six primary ensemble outcomes, not a claim that all 21 E6 outcomes or the six-experiment project are complete.

| Repetition | Equal-weight outcome | Learned-weight outcome | Cause |
|---|---|---|---|
| 1 | unavailable dependency | unavailable dependency | KDE member evaluation timeout under the fixed phase policy |
| 2 | unavailable dependency | unavailable dependency | KDE member evaluation timeout under the fixed phase policy |
| 3 | unavailable dependency | unavailable dependency | KDE member evaluation timeout under the fixed phase policy |

The CSV includes exact keys, scientific availability reasons, phase limits and observed phase durations/RSS. Raw process receipts remain in local operational evidence and are excluded from public delivery.
