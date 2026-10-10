# Comparison: batch_main against batch_shuffle

| Metric | batch_main | batch_shuffle | Note |
| --- | --- | --- | --- |
| Games finished | 10 | 10 |  |
| Doctor voted for provably town | 0 of 4 | 2 of 9 | Should be 0. |
| Detective voted for a cleared player | 0 of 7 | 0 of 8 | Should be 0. |
| Detective voted for a found mafia | 4 of 4 | 4 of 4 | Higher is better. |
| False statements about the record | 0 of 6 | 0 of 13 | Lower is better. |
| Vote reasoning names the target | 100.0% | 100.0% |  |
| Votes resting on concrete evidence | 60.0% | 68.3% |  |
| Votes resting on nothing specific | 7.1% | 9.8% | Lower is better. |
| Town followed a false detective claim | 0 of 1 | 0 of 1 | Lower is better. |
| Town wins (not a quality measure) | 9 | 6 |  |
| Average days | 1.8 | 2.4 |  |
| Invalid actions | 0 | 0 | Should stay at 0. |
| API errors | 0 | 0 |  |
| Model calls per game | 28.0 | 37.6 |  |
| Tokens per game | 37,930 | 55,937 |  |
| Detective check: first listed in prompt | 84.6% of 13 | 29.4% of 17 | Chance is about 21.4%. |
| Mafia kill: first listed in prompt | 55.6% of 18 | 33.3% of 24 | Chance is about 24.3%. |
| Doctor protection: first listed in prompt | 37.5% of 16 | 13.6% of 22 | Chance is about 18.0%. |
| Day vote: first listed in prompt | 28.6% of 70 | 31.7% of 82 | Chance is about 26.5%. |
| Detective check: earliest seat | 84.6% of 13 | 47.1% of 17 | Chance is about 21.4%. |
| Mafia kill: earliest seat | 55.6% of 18 | 37.5% of 24 | Chance is about 24.3%. |
| Doctor protection: earliest seat | 37.5% of 16 | 36.4% of 22 | Chance is about 18.0%. |
| Day vote: earliest seat | 28.6% of 70 | 23.2% of 82 | Chance is about 26.5%. |
| Town vote accuracy | 54.7% | 46.0% | Random guessing scores about 27%. |
| Ejections that hit mafia | 9 of 15 | 6 of 18 |  |
| Power roles ejected by town | 5 | 3 |  |
| Mafia kills aimed at power roles | 22.2% | 37.5% | Chance is 40% with 6 players. |
| Kills stopped by the doctor | 7 of 18 | 11 of 24 |  |
| Detective found a mafia | 3 | 7 |  |
| Games where the doctor outed themself | 0 | 0 |  |
| Agree with the last speaker | 6.0% | 5.2% |  |
| Near duplicate speeches | 0.0% | 0.0% |  |
| Format leaks | 0 | 0 | Should stay at 0. |

## Judge review (same seeds, same judge)

Rated by `gemini-3.6-flash` and `gemini-3.6-flash`. Only the games both batches had judged are comparable, so check the game counts: 10 against 10.

| Metric | batch_main | batch_shuffle | Note |
| --- | --- | --- | --- |
| Games judged | 10 | 10 | |
| Decisions rated | 117 | 145 | |
| Sound | 64.1% | 69.7% | Higher is better. |
| Weak | 33.3% | 29.0% | Thin evidence or an overlooked clue. |
| Illogical | 2.6% | 1.4% | Lower is better. |
| Day votes rated sound | 40.0% | 46.3% | |
| Villager decisions rated sound | 12.1% | 22.2% | |
| Game logic score, 1 to 5 | 2.7 | 2.8 | |

## Same seeds, same roles

5 of 10 seeds ended with the same winner.

| Seed | batch_main winner | batch_shuffle winner | batch_main days | batch_shuffle days |
| --- | --- | --- | --- | --- |
| 100 | town | mafia | 1 | 3 |
| 101 | mafia | town | 3 | 2 |
| 102 | town | town | 2 | 3 |
| 103 | town | town | 2 | 1 |
| 104 | town | mafia | 1 | 3 |
| 105 | town | mafia | 2 | 3 |
| 106 | town | town | 1 | 2 |
| 107 | town | mafia | 3 | 3 |
| 108 | town | town | 2 | 2 |
| 109 | town | town | 1 | 2 |
