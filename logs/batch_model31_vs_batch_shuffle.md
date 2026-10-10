# Comparison: batch_shuffle against batch_model31

| Metric | batch_shuffle | batch_model31 | Note |
| --- | --- | --- | --- |
| Games finished | 10 | 10 |  |
| Doctor voted for provably town | 2 of 9 | 0 of 6 | Should be 0. |
| Detective voted for a cleared player | 0 of 8 | 0 of 10 | Should be 0. |
| Detective voted for a found mafia | 4 of 4 | 3 of 3 | Higher is better. |
| False statements about the record | 0 of 13 | 0 of 6 | Lower is better. |
| Vote reasoning names the target | 100.0% | 94.6% |  |
| Votes resting on concrete evidence | 68.3% | 58.1% |  |
| Votes resting on nothing specific | 9.8% | 12.2% | Lower is better. |
| Town followed a false detective claim | 0 of 1 | 0 of 1 | Lower is better. |
| Town wins (not a quality measure) | 6 | 7 |  |
| Average days | 2.4 | 1.9 |  |
| Invalid actions | 0 | 0 | Should stay at 0. |
| API errors | 0 | 0 |  |
| Model calls per game | 37.6 | 31.4 |  |
| Tokens per game | 55,937 | 42,396 |  |
| Detective check: first listed in prompt | 29.4% of 17 | 18.8% of 16 | Chance is about 22.2%. |
| Mafia kill: first listed in prompt | 33.3% of 24 | 57.9% of 19 | Chance is about 27.1%. |
| Doctor protection: first listed in prompt | 13.6% of 22 | 21.1% of 19 | Chance is about 20.2%. |
| Day vote: first listed in prompt | 31.7% of 82 | 29.7% of 74 | Chance is about 28.3%. |
| Detective check: earliest seat | 47.1% of 17 | 68.8% of 16 | Chance is about 22.2%. |
| Mafia kill: earliest seat | 37.5% of 24 | 52.6% of 19 | Chance is about 27.1%. |
| Doctor protection: earliest seat | 36.4% of 22 | 52.6% of 19 | Chance is about 20.2%. |
| Day vote: earliest seat | 23.2% of 82 | 18.9% of 74 | Chance is about 28.3%. |
| Town vote accuracy | 46.0% | 42.9% | Random guessing scores about 27%. |
| Ejections that hit mafia | 6 of 18 | 7 of 17 |  |
| Power roles ejected by town | 3 | 3 |  |
| Mafia kills aimed at power roles | 37.5% | 31.6% | Chance is 40% with 6 players. |
| Kills stopped by the doctor | 11 of 24 | 7 of 19 |  |
| Detective found a mafia | 7 | 4 |  |
| Games where the doctor outed themself | 0 | 0 |  |
| Agree with the last speaker | 5.2% | 8.6% |  |
| Near duplicate speeches | 0.0% | 0.0% |  |
| Format leaks | 0 | 0 | Should stay at 0. |

## Judge review (same seeds, same judge)

Rated by `gemini-3.6-flash` and `gemini-3.6-flash`. Only the games both batches had judged are comparable, so check the game counts: 10 against 10.

| Metric | batch_shuffle | batch_model31 | Note |
| --- | --- | --- | --- |
| Games judged | 10 | 10 | |
| Decisions rated | 145 | 128 | |
| Sound | 69.7% | 68.8% | Higher is better. |
| Weak | 29.0% | 29.7% | Thin evidence or an overlooked clue. |
| Illogical | 1.4% | 1.6% | Lower is better. |
| Day votes rated sound | 46.3% | 47.3% | |
| Villager decisions rated sound | 22.2% | 27.3% | |
| Game logic score, 1 to 5 | 2.8 | 3.2 | |

## Same seeds, same roles

5 of 10 seeds ended with the same winner.

| Seed | batch_shuffle winner | batch_model31 winner | batch_shuffle days | batch_model31 days |
| --- | --- | --- | --- | --- |
| 100 | mafia | town | 3 | 2 |
| 101 | town | town | 2 | 2 |
| 102 | town | town | 3 | 2 |
| 103 | town | mafia | 1 | 2 |
| 104 | mafia | town | 3 | 1 |
| 105 | mafia | mafia | 3 | 3 |
| 106 | town | mafia | 2 | 3 |
| 107 | mafia | town | 3 | 1 |
| 108 | town | town | 2 | 1 |
| 109 | town | town | 2 | 2 |
