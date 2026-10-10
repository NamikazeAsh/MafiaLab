# Development log

A running record of what was built, what was tried, and what the results showed. Newest entries are at the bottom. Every experiment and change gets an entry, with the commands needed to reproduce it.

## Where things stand

* **Engine and rules:** stable. 6 to 10 players, default mafia count 1 for 6 players.
* **Players:** Gemini models through an OpenAI compatible client. Default model `gemini-3.5-flash-lite`.
* **Viewer:** live and replay, Among Us style, Mystery mode by default.
* **What counts as quality:** logical play, not winning. Reports lead with hard logic checks and a judge review, and win rates are labelled as not a quality measure.
* **Measured quality:** 0 invalid actions over 30 real games on two models. All 30 are judged by one primary judge (390 decisions): 67.7% sound, 30.5% weak, 1.8% illogical. The option shuffle removed the bias toward the first listed name, but neither it nor the second model measurably changed reasoning quality. The weak spot is thin evidence in villagers' day votes (20.6% of villager decisions sound). The one clear mistake is the doctor ignoring what a blocked kill proves.
* **Fixes tested by replay, not yet adopted:** stating the doctor's own conclusion as a fact removed the mistake (16 of 108 votes to 0 of 108). An instruction for villagers to name a concrete fact was preferred by a blind judge in 7 of 7 decisive pairs. See the replay entry and section 2.6 of the quality report.
* **Information leaks:** none found. 992 real prompts across 30 games audited, 0 leaks (see the audit entry). Tells in public speech cannot be ruled out.
* **Names:** the roster is now Ay, Bee, Cee, Dee, Ey, Foo, Gi, Himothy (then Ivy and Jojo). Batches before 2026-10-03 used Ann, Bob, Cy, and so on.
* **Open problems:** a smaller preference for early seat names in night actions, a balance that is still noisy at 10 games, and no memory between games yet.
* **Constraint:** the free tier allows 500 requests per day for each lite model and only 20 per day for each stronger model (used as judges). Plan about 10 games per lite model per day.

Folders and files referred to below:

| Path | What it is |
| --- | --- |
| `logs/batch_main.json` | Summary of the baseline batch (10 games, no shuffle) |
| `logs/batch_shuffle.json` | Summary of the shuffled batch (same 10 seeds) |
| `logs/batch_model31.json` | Summary of the second model batch (same seeds, shuffle on) |
| `logs/*_report.md` and `logs/batch_shuffle_vs_batch_main.md` | Generated reports |
| `logs/game_*.jsonl` and `logs/trace_*.jsonl` | One event log and one prompt trace per game |
| `logs/archive_20260929_151725/` | Older games moved aside, safe to delete |

---

## 2026-09-29: Foundation

**Goal:** a Mafia simulator where language models play against each other, with private night chat, a doctor, and a detective.

**Built:**
* `mafia/engine`: state, rules, visibility, and the game loop. The engine uses no AI and is deterministic for a seed.
* `mafia/agents`: an agent interface, a random agent for free testing, and the LLM agent (prompt builder and reply parser).
* `mafia/llm/client.py`: an OpenAI compatible client using only the standard library, with a request rate cap, retries, an on disk cache, and token counting.
* `run.py`: play one game in the terminal and write a JSONL event log.

**Key design decisions:**
* Information hiding is structural. Every event has an audience, and `view_for()` builds each player's view from the events that player may see. Tests assert that a villager never sees mafia chat or roles.
* A `setup` event holds all roles and has an empty audience, so the log and the viewer can see it and no player can.
* Invalid model replies are retried, then replaced with a safe default, so a bad reply cannot break a game.
* Win rule: town wins when the mafia are gone, and the mafia win when they are at least as many as the town.

---

## 2026-09-29: First real games and prompt fixes

Real games on Gemini exposed a series of problems. Each was fixed and checked in a later game.

| Problem seen | Cause | Fix |
| --- | --- | --- |
| `__error__` appeared as a chat message | An API exception was swallowed and the placeholder passed the speech check | Errors are now logged and counted, and the run aborts after 6 |
| 404 from the API | The default model name was outdated | Changed to `gemini-3.5-flash-lite` (the API named it in the error) |
| Players invented a past on Night 1 ("nobody died last night") | One word replies gave the model nothing to anchor on | Prompt now states "this is the very first night" |
| Mafia chat said one target and the vote chose another | The vote prompt did not stress the team plan | The mafia now vote in rounds, see each other's votes, and must agree on one target |
| Players always spoke in the same order, so the last speaker was called "silent" | Fixed seat order | Speaking order is shuffled each day |
| Votes piled onto the first voter | Votes were sequential and public | Votes are secret until everyone has voted, then revealed together |
| Detective and doctor outed themselves on day 1 | No secrecy guidance | Added role secrecy strategy to the prompts |
| Town played irrationally | Personas gave attitudes such as gut driven or paranoid | Personas are now speaking style only |
| Mafia conceded ("good game") | No instruction against it | Prompt says never concede |

**Structural balance with random players** (1500 games each, no skill, so only a floor):

| Setup | Town wins | Mafia wins |
| --- | --- | --- |
| 6 players, 1 mafia | 33% | 67% |
| 6 players, 2 mafia | 7% | 93% |
| 7 players, 1 mafia | 39% | 61% |
| 7 players, 2 mafia | 9% | 91% |
| 8 players, 2 mafia | 13% | 87% |
| 10 players, 3 mafia | 5% | 95% |

**Decision:** default mafia count is 1 for 6 players, 2 for 7 to 9, and 3 for 10 (`rules.default_mafia`). `--mafia N` overrides it. With 1 mafia a game has no mafia chat, so that step is skipped.

---

## 2026-09-29: Web viewer

**Built:** a stdlib HTTP server (`mafia/web`) and a plain HTML, CSS, and JavaScript viewer (`web/`). It plays live games and replays saved ones.

**Features:** player ring around a cafeteria table, original SVG crewmates, day and night scenes, ejection and kill effects, chat, votes, and night log tabs, a timeline scrubber, speed control, Full view and Mystery mode, and a setup form. A free demo uses random players.

**Bugs found by driving real Chrome through the DevTools protocol:**
* `POST` bodies were not read, so the next request on a kept alive connection was corrupted. The server now always reads the body, and drains a bounded amount of oversized ones.
* Pasting a new `#game=` link into an open tab did nothing. The app now listens for hash changes.
* Animations did not run because Windows reports "reduce motion". Added an Animations toggle that defaults to the system setting.
* The 10 player ring was crowded. Characters are smaller and the ring wider from 9 players up.
* Browser tabs dropping a connection printed tracebacks. The server now ignores connection resets.

**Security:** the server listens on 127.0.0.1 only, rejects a wrong Host header, and requires a custom header and a local origin on `POST`, so another web page cannot start games and spend the API quota.

---

## 2026-09-29: Demo default and lobby viewing mode

**Problem:** the user saw players saying "I am Ann, day 1". Those lines come from the random demo players. The setup form had the demo ticked by default.

**Changes:**
* The form defaults to real players when a Gemini key exists, and remembers the last choice.
* Demo games show a "DEMO PLAYERS, NO AI" badge.
* The lobby has a "How do you want to watch?" choice. **Mystery mode** is the default and applies to new games and replays. Switching to Full view during a game asks for confirmation. The saved games list hides the winner in Mystery mode.

---

## 2026-09-29: Batch tooling and the baseline batch

**Goal:** measure play quality over many games instead of judging single games.

**Built:**
* `batch.py` and `mafia/batch.py`: play N games with consecutive seeds. A summary is saved after every game, so a batch resumes if interrupted. It stops after 2 failed games in a row.
* `analyze.py` and `mafia/analysis.py`: score a batch for reliability, outcomes, voting accuracy against random guessing, role secrecy, writing quality, and example quotes. `--baseline` compares two batches.

**Setup:** `python batch.py --games 10 --seed-start 100 --rpm 10 --summary logs/batch_main.json`. 6 players, 1 mafia, `gemini-3.5-flash-lite`.

**Result of the first 9 games:** 0 invalid actions, 0 API errors, about 31 calls and 41k tokens per game. Town won 8 of 9. Game 10 failed with a 429 error.

**Quota finding:** the 429 was the daily free tier cap. The full message read `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 500 requests, per model. The client had retried it for 24 minutes with no chance of success.

**Fixes from this step:**
* The client fails at once on a daily cap and honors the server's suggested retry delay for per minute limits.
* The analyzer ignores quoted text, so a villager quoting someone's claim is not counted as a fake claim (5 flagged, 2 genuine).
* Seat order bias was spotted by eye (the mafia killed Ann or Bob on night 1 in 9 of 9 games) and then measured: see the next entry.

---

## 2026-10-03: Option order shuffle experiment

**Hypothesis:** the model picks the first name in a list, which makes night choices arbitrary and inflates town's win rate (the detective checks the first listed player, the mafia kills the first listed player).

**Baseline** (`batch_main`, seeds 100 to 109, seed 109 resumed from the cache after the quota failure):

* Detective check picked the first listed name 84.6% of the time (13 checks), chance about 21%.
* Mafia kill 55.6% (18), chance about 24%. Doctor 37.5% (16), chance 18%. Day votes 28.6% (70), chance 26.5%, so no bias on votes.

**Change:** `shuffled()` in `mafia/agents/llm_agent.py` shows the option list and the "Alive" list in an order that changes with every request but is reproducible (seeded from player, day, phase, request kind, and number of visible events).

**Run:** same 10 seeds, so the roles and personas (and in practice the day 1 speaking order) match the baseline. The games themselves still diverge, because the models sample at temperature 0.8. **Confound:** the baseline games ran on 2026-09-29 (seed 109 on 2026-10-03) and this batch on 2026-10-03, four days apart, so a change in how the provider serves the model cannot be ruled out.
`python batch.py --games 10 --seed-start 100 --rpm 10 --summary logs/batch_shuffle.json`

| Metric | Baseline | Shuffled |
| --- | --- | --- |
| Town wins | 9 of 10 | 6 of 10 |
| Average days | 1.8 | 2.4 |
| Invalid actions, API errors | 0, 0 | 0, 0 |
| Model calls per game | 28.0 | 37.6 |
| Tokens per game | 37,930 | 55,937 |
| Town vote accuracy (random guessing 27%) | 54.7% | 46.0% |
| Ejections that hit the mafia | 9 of 15 | 6 of 18 |
| Power roles ejected by town | 5 | 3 |
| Mafia kills aimed at power roles (chance 40%) | 22.2% | 37.5% |
| Kills stopped by the doctor | 7 of 18 | 11 of 24 |
| Detective found a mafia | 3 | 7 |
| Doctor outed themselves | 0 games | 0 games |
| Agree with the last speaker | 6.0% | 5.2% |
| Near duplicate speeches, format leaks | 0%, 0 | 0%, 0 |

**Same seeds, same roles:** only 5 of 10 seeds ended with the same winner, so single games are very noisy.

**List position bias, measured from the saved prompts** (`logs/trace_*.jsonl`):

| Action | Before | After | Chance |
| --- | --- | --- | --- |
| Detective check | 84.6% | 29.4% | 21% |
| Mafia kill | 55.6% | 33.3% | 24% |
| Doctor protection | 37.5% | 13.6% | 18% |
| Day vote | 28.6% | 31.7% | 27% |

**Conclusion:**
* The shuffle removed the list position bias. Night choices are now close to chance with respect to list position.
* The drop in town wins (9 to 6 of 10) fits the idea that the old bias helped town, but 10 against 10 games is not enough to be sure (Fisher exact test, p about 0.3).
* A smaller preference remains for the **earliest seat** names (Ann and Bob) in night actions: 47% of detective checks (17), 37.5% of kills (24), and 36% of doctor saves (22), against about 22% to 27% by chance. Day votes show none. It is not yet known whether this is about the names, or about seat order showing up elsewhere in the history (the `Game start` line lists players in seat order).

**Analyzer correction:** the metric first called "first name shown" measured seat order, not list position, after the shuffle. It now reports both, "first listed in the prompt" (from the traces) and "earliest seat".

---

## 2026-10-03: Second model batch

**Goal:** check that the conclusions do not depend on one model, and use a separate daily quota (quotas are per model).

**Run:** `python batch.py --games 10 --seed-start 100 --rpm 10 --model gemini-3.1-flash-lite --summary logs/batch_model31.json`, shuffle on, same seeds, old names.

**Result:** 10 of 10 games finished with 0 invalid actions and 0 API errors. About 31 calls per game, but 5.4 minutes per game against 3.8 for `gemini-3.5-flash-lite`, because the model replies more slowly at the same request rate. Town won 7 of 10. The leak audit is clean (315 prompts, 6,756 history lines, 0 leaks). The quality comparison is in the "Hard logic checks" entry below, since wins are not the measure that matters here.

---

## 2026-10-03: Information leak audit

**Question (from the user):** is information leaking between the players?

**Why it needs evidence:** the design says each prompt holds only what that player may see, and unit tests check it, but the tests do not look at what was really sent to the model.

**Built:** `mafia/audit.py` and `audit.py`. For every saved prompt (`logs/trace_*.jsonl`) it checks that:
* each line of game history is an event whose audience includes that player (the game log records the audience of every event),
* the role stated in the system prompt is the player's real role,
* the list of fellow mafia matches the real mafia, and is empty for everyone else.

The `setup` event has an empty audience, so any prompt that contains it is flagged. `tests/test_audit.py` injects four kinds of leak (mafia chat into a villager's prompt, another player's thought, the spectator only roles line, a wrong role) and checks each is caught, so a clean result means something.

**Run:** `python audit.py logs/batch_main.json logs/batch_shuffle.json logs/batch_model31.json`

| Batch | Games | Prompts | History lines checked | Leaks | Role mismatches | Teammate mismatches |
| --- | --- | --- | --- | --- | --- | --- |
| `batch_main` | 10 | 299 | 6,330 | 0 | 0 | 0 |
| `batch_shuffle` | 10 | 378 | 9,745 | 0 | 0 | 0 |
| `batch_model31` (first 5 games) | 5 | 153 | 3,061 | 0 | 0 | 0 |

**Other channels checked:**
* **Response cache.** The cache key covers the model and the whole message list, including the player's name, role, and persona, so one player's reply is never served to another. It does serve identical prompts. In `batch_main` seeds 101 and 102, `Di the detective` had the same persona and an identical night 1 prompt, so game 102 reused game 101's reply. Identical prompts hold identical information, so nothing leaked, but those two choices are not independent. Only 1 to 3 calls per batch are affected.
* **Provider side.** Each request carries the whole prompt and the endpoint keeps no conversation between requests. This was not verified from the provider's side.
* **Tells in public speech.** Players are the same model, so mafia could in principle give themselves away. On day 1, before anyone had real information, town votes hit the mafia in 42% of 31 votes in `batch_main` and 15% of 20 in `batch_shuffle`, against about 22% by chance. Votes in a game are strongly correlated (a bandwagon gives 5 hits at once), so this is about 10 independent outcomes per batch. The two batches disagree, so there is no consistent signal either way.

**Conclusion:** no structural leak in 830 prompts. Behavioral tells cannot be ruled out, only shown to be small or absent in this sample.

**Methodology trap found:** rerunning the same seeds with the same code replays the cache and returns the earlier replies, not new samples. That is right for resuming a batch and wrong for replicates. Added `--no-cache` to `batch.py` (`cache=False` in `build_agents`). Use new seeds or `--no-cache` for a replicate.

---

## 2026-10-03: Player names changed

**Change:** the roster is now `Ay, Bee, Cee, Dee, Ey, Foo, Gi, Himothy` (requested by the user), plus `Ivy` and `Jojo` as players 9 and 10 so games of 9 and 10 players still work (`Jo` was changed to `Jojo` at the user's request). The list is `NAMES` in `mafia/setup.py`. Checked at 6, 8, 9, and 10 players.

**Effect on experiments:** each log stores its own roster, so old batches and the viewer are unaffected. **New batches are not directly comparable to the old ones**, because the earlier measurements showed a preference for the earliest seat names, and the names themselves are now different. This is also a cheap experiment on the open question below: repeat the shuffled batch with the same seeds and the new names. If the early seat preference stays with the first seat, it is about seat order. If it follows the old names, it is about the names.

The second model batch (`batch_model31`) was started before this change and keeps the old names throughout.

---

## 2026-10-03: Reports regenerated with the audit included

**Why:** `logs/batch_main_report.md` was stale (written when only 9 games had finished), and the reports did not yet cover information control.

**Change:** `python analyze.py` now runs the leak audit and puts an "Information leak audit" section in every report (prompts checked, history lines checked, leaks, role mismatches, teammate mismatches). The report also has the corrected bias rows (first listed in the prompt, from the saved prompts, and earliest seat).

**Regenerated:**
* `logs/batch_main_report.md` (10 games)
* `logs/batch_shuffle_report.md` (10 games) and `logs/batch_shuffle_vs_batch_main.md`
* `logs/batch_model31_report.md` and `logs/batch_model31_vs_batch_shuffle.md` (partial: the batch had 5 of 10 games finished at the time, and the report must be regenerated when it ends)

Regenerate any of them with `python analyze.py logs/<summary>.json --baseline logs/<other summary>.json`.

Also changed in the roster: `Jo` became `Jojo` (see the names entry).

---

## 2026-10-03: Quality means logical play, not winning

**Direction from the user:** it does not matter who wins. What matters is whether players win or lose **logically**. My earlier reports leaned on win rates and balance, which is the wrong lens. A town win can come from a bad vote that happened to land, and a loss can follow sound reasoning.

**What I looked at first:** the day votes and each player's private reasoning, with roles visible. Seed 105 of `batch_shuffle` (old names) shows the kind of failure that matters. The doctor (Bob) protected Cy on nights 2 and 3 and nobody died either night. That proves the mafia aimed at Cy, so Cy cannot be mafia. In the final three Bob still voted Cy out, and the mafia won. It is a logical failure that exists whatever the result. The same game's day 1 lynch of the detective rested only on "he is deflecting", which is thin evidence but nothing a player could do better with no information.

**Plan:** measure reasoning in two layers. Hard checks that need no AI (next entry), and a judge model that rates each decision against what the player knew (the entry after). Win rates stay in the report but are labelled "not a quality measure".

---

## 2026-10-03: Hard logic checks

**Built:** `mafia/logic.py`, wired into `analyze.py`, with 16 tests. Each check uses only the game log and asks whether a decision or a statement fits what the player knew or the public record. They are conservative and only count cases the log can settle.

| Check | What it tests |
| --- | --- |
| Doctor vote against a provably town player | A kill that was blocked by the doctor's protection means the mafia aimed at that player, so they are not mafia. Voting them out ignores what the doctor knows. |
| Detective vote against a player they cleared | Ignoring their own check result |
| Detective vote for a mafia they found | Acting on their own result (higher is better) |
| Mafia vote for their own partner | Rarely sensible |
| False statements about the public record | "X voted for Y", "X was the detective", "nobody died last night", "X claimed to be the doctor", each checked against the log. Quoted text and hypotheticals are skipped. Mafia lying about their own role is not counted. |
| Reasoning names the player voted for | Whether the private reason is about the person actually voted for |
| What each vote rests on | Concrete evidence (a claim, a vote record, a night result, an inconsistency), behavior only (defensive, evasive, quiet), or nothing specific |
| Response to detective claims | Whether the town voted for the accused after a true claim, and whether it was fooled by a false one |

**Bugs found in my own checks while building them:**
* A real detective who named several players was scored as making several false claims. Fixed: a real detective's claim is only judged when it names a mafia they actually found, and for a bluff the accused is the name nearest the word mafia.
* Name matching in vote reasoning was case sensitive, but one player writes names in lowercase, so it gave false alarms. Fixed.

**Results** (same 10 seeds in each batch, old names; `python analyze.py logs/<summary>.json`):

| Check | Baseline 3.5 lite | Shuffled 3.5 lite | Shuffled 3.1 lite |
| --- | --- | --- | --- |
| Doctor voted a provably town player | 0 of 4 | **2 of 9** | 0 of 6 |
| Detective voted a player they had cleared | 0 of 7 | 0 of 8 | 0 of 10 |
| Detective voted a mafia they had found | 4 of 4 | 4 of 4 | 3 of 3 |
| False statements about the record | 0 of 6 | 0 of 13 | 0 of 6 |
| Reasoning names the player voted for | 100% | 100% | 94.6% |
| Votes resting on concrete evidence | 60.0% | 68.3% | 58.1% |
| Votes resting on behavior only | 32.9% | 22.0% | 29.7% |
| Votes resting on nothing specific | 7.1% | 9.8% | 12.2% |
| Town followed a true detective claim | 2 of 4 | 4 of 4 | 3 of 3 |
| Town followed a false detective claim | 0 of 1 | 0 of 1 | 0 of 1 |
| Invalid actions, API errors | 0, 0 | 0, 0 | 0, 0 |
| Town wins (not a quality measure) | 9 of 10 | 6 of 10 | 7 of 10 |

**What this says:**
* The reasoning mostly holds up. The detective never voted against a player they had cleared (0 of 25 across the three batches) and always acted on a mafia they had found (11 of 11). The town followed true detective claims in 9 of 11 cases and was not fooled by any of the 3 false ones.
* The one real failure is the doctor ignoring the proof from a blocked kill: 2 of 19 doctor votes, both in `batch_shuffle`. The doctor is the role whose key inference is not handed to it, so this is where a prompt hint could help.
* About 1 vote in 10 rests on nothing specific, and about a quarter to a third rest only on how someone talked.
* The false statement check found nothing, but it had very few verifiable statements to check (6, 13, and 6), so it has little power.
* Caveats: roughly 10 to 20 chances per check per batch, so a difference of a couple of cases is not significant. The text patterns will miss unusual phrasing.

---

## 2026-10-03: Judge model

**Why:** hard checks only catch what can be settled mechanically. A weak lynch built on thin evidence, or a plausible but unsupported accusation, passes them.

**Built:** `mafia/judge.py` and `judge.py`. For each game it builds a casebook that shows the judge every secret role, every speech, each decision's private reasoning, and what the decider privately knew (the detective's earlier checks, the doctor's protections and what followed, the mafia's partner). The judge rates every decision (day votes, protections, checks, mafia kills) as **sound**, **weak** (thin evidence or an overlooked clue), or **illogical** (contradicts something the player knew, or rests on a false fact), with a reason tag. It is told to judge against only what that player knew at that moment and never by who turned out to be mafia. It also scores the whole game 1 to 5. Results are saved per game and resumed on a rerun.

**Judge model:** `gemini-3.5-flash`, a different and stronger model than the players, on its own daily quota. `python judge.py logs/batch_shuffle.json` (add `--model` to change it).

**Safeguard:** the hard checks serve as an answer key for the votes they can settle. The report shows how often the judge rated a known violation as not sound, and how often it rated a known good act as sound.

**Two bugs found on the first real game (seed 105 of `batch_shuffle`):**
* The judge returned a reply cut off in the middle of its JSON. `gemini-3.5-flash` is a thinking model, and its hidden reasoning used almost the whole 4,000 token budget, leaving about 157 tokens for the answer. Fixed with a 16,000 token budget, and a reply that rates fewer than 90% of the decisions is treated as unusable.
* The retry sent the identical prompt, so the response cache returned the same cut off reply and the retry did nothing. Fixed: a retry changes the prompt.

**First check:** on seed 105 the judge flagged exactly the doctor's final vote as illogical, with the right reason (the doctor knew his protection had blocked two kills, so Cy was town). It rated the other 16 decisions sound, including the weak day 1 lynch, so it was too lenient. The rubric now says a vote resting only on how someone talked is weak, and that illogical is reserved for real contradictions.

**Quota constraint:** the free tier allows only **20 requests per day** for `gemini-3.5-flash` (read from the 429 error: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 20), and the other non lite flash models behave the same. The Pro model has a limit of 0. Judging all 30 games with one model was therefore impossible in a day. I added `--max-games N` (judge the first N seeds in seed order) and used three judges, each on its own quota:

| Judge | Games rated | Files |
| --- | --- | --- |
| `gemini-3.6-flash` (primary) | 15: first 6 seeds of `batch_main` and `batch_shuffle`, first 3 of `batch_model31` | `logs/judge36_*.json` |
| `gemini-3.8-flash` | 13 (stopped by its quota) | `logs/judge38_*.json` |
| `gemini-3.5-flash` | 8 (stopped by its quota) | `logs/judge35_*.json` |

Results, agreement between judges, the comparison across batches, and the findings are written up in [QUALITY_REPORT.md](QUALITY_REPORT.md). Headlines: 70.9% of 196 decisions sound, 27.6% weak, 1.5% illogical. Day votes were only 49% sound, and villagers' decisions 23.5% sound, nearly all because the accusation rested on thin evidence. Mafia decisions 98% sound. The judges agreed closely (3.6 against 3.8: 94.6% to 100% same verdict, kappa 0.92 to 1.0). The one decision all three judges called illogical was the doctor's blunder.

Tools added in this step: `mafia/judge.py`, `judge.py`, `compare_judges.py` (judge against judge agreement), `--max-games`, the `--judge` and `--baseline-judge` options of `analyze.py`.

---

## 2026-10-03: Final report written

`docs/QUALITY_REPORT.md` consolidates the leak audit, the hard checks, the judge review, the comparison of batches, and the limits of the evidence.

**Methodology added to the report (section 1, plus three appendices),** covering: the study design and its confounds, the game and the exact prompts and sampling settings, what was recorded, the leak audit (and what it cannot see), the choice bias measure, every hard check with its definition, the judge (casebook, what is rated, the rules, parsing, token budget, retries, the three judge models and why, the answer key, agreement statistics), the secondary measures, the statistics, how the tools were tested, the weaknesses of the method, how the method changed during the work, and how to reproduce. Appendix A holds the judge's instructions word for word, Appendix B shows the format the judge reads, and Appendix C lists the text patterns.

**Weaknesses of the method that the report now states plainly:** the judge's instructions contain the doctor inference rule, so catching that mistake shows the judge applies a stated rule, not that it finds such inferences unprompted; the answer key has only 1 known violation and 5 known good acts; the instructions were tightened once after seeing the judge's output on seed 105, which is in the evaluated set; the hard checks were designed after reading games; the logged "reasoning" is a rationale written beside the action, not hidden thinking; the leak audit checks delivery against the audience tags and cannot catch a mis-tagged event; the players and all judges are one model family; there are no human ratings; and the baseline ran four days before the other batches.

**What is not established:** whether option shuffling or the second model improved reasoning. On seeds 100 to 102 both look better than the baseline (sound 59.5%, 80.0%, 84.6%), but on the wider seeds 100 to 105 the baseline and the shuffled batch are close (64.7% and 69.7%). The samples are too small to tell.

**Judging still to do (needs another day of quota):** the other 3 seeds of `batch_model31` with `gemini-3.6-flash`, and seeds 106 to 109 of the first two batches. Resume with the same commands, for example `python judge.py logs/batch_model31.json --model gemini-3.6-flash --max-games 6 --out logs/judge36_batch_model31.json`.

---

---

## 2026-10-03: README brought up to date

**Why:** it still described an earlier project: the layout was missing the batch, analysis, logic, audit, and judge code, the limits said a batch runner was "planned first" and that win rates were the thing to measure, the quality section had a duplicated sentence and an unformatted flag, and it said Node might be needed.

**Changed:** added the quality tools to the feature list and the file layout; a tool table for `batch.py`, `audit.py`, `judge.py`, `analyze.py`, and `compare_judges.py` with their options; the player names; the option shuffle and why it exists; the free tier budget (about 500 requests per day for lite models, about 20 for judges); `--no-cache`; the quality findings in one paragraph with a link to the report; the test count and what it covers; and a rewritten "Known limits" that reflects the current evidence, the seat name question, and the next ideas to test. Moved "Measuring quality" ahead of the tests and security notes.

**Checked:** code fences balanced, every link and image resolves, every flag in the tool table exists in the code, every file in the layout exists, and no stale phrases remain.

---

## 2026-10-09: All 30 games judged

**Why:** only 15 of the 30 games had been rated by the primary judge, because each stronger model allows 20 requests per day. With a new day's quota, `gemini-3.6-flash` rated the other 15 with the same instructions and settings (`python judge.py logs/<batch>.json --model gemini-3.6-flash --max-games 10 --out logs/judge36_<batch>.json`, which resumes and skips finished games).

**Results** (judge `gemini-3.6-flash`, all 10 games per batch):

| Batch | Decisions | Sound | Weak | Illogical | Day votes sound | Villagers sound | Mean share sound per game | Game score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline, 3.5 lite | 117 | 64.1% | 33.3% | 2.6% | 40.0% | 12.1% | 61.7% | 2.7 |
| Shuffled, 3.5 lite | 145 | 69.7% | 29.0% | 1.4% | 46.3% | 22.2% | 69.4% | 2.8 |
| Shuffled, 3.1 lite | 128 | 68.8% | 29.7% | 1.6% | 47.3% | 27.3% | 69.5% | 3.2 |
| All three | 390 | 67.7% | 30.5% | 1.8% | 44.7% | 20.6% | | 2.9 |

**What changed in the conclusions:**
* **A subset result reversed.** On the first three seeds the baseline, shuffled batch, and second model scored 59.5%, 80.0%, and 84.6% sound, which looked like a large gain from the shuffle and the second model. On all ten seeds they are within 6 points of each other and the differences are not significant (Fisher exact p = 0.36 to 0.90, with decisions treated as independent, which overstates the evidence). The report now says so and warns against trusting subsets.
* **The weak spot is sharper.** Villagers' decisions were 20.6% sound and 76.5% weak. Of 127 decisions not rated sound, 110 were unsupported accusations.
* **The answer key grew:** 2 known violations (both rated illogical) and 11 known good acts (all rated sound).
* **Seven decisions were rated illogical in total:** two doctor blunders, three false statements of fact made while reasoning, and two reasons that contradicted the player's own statement or role knowledge. Two other judges flagged one more villager contradiction that the primary judge rated weak, so 7 is a lower bound.

Reports regenerated: `logs/batch_main_report.md`, `logs/batch_shuffle_report.md`, `logs/batch_model31_report.md`, and the two comparison files. The quality report's numbers were updated to the full set.

---

## 2026-10-09: Replay experiments on the two weaknesses

**Goal:** test candidate fixes for the doctor's mistake and for villagers' thin evidence, without needing hundreds of new games.

**Built:** `mafia/ablate.py` and `ablate.py` (15 tests). It takes real prompts from the saved traces where the situation arose, asks the model again many times with and without one change, and compares. The cache is off so every reply is fresh, the two arms alternate prompt by prompt, and results are saved per prompt so a quota stop resumes. The doctor cases are read from the prompt itself (a protection, a quiet night, the protected player still alive). The villager comparison also uses a blind pairwise judge. The full method is in section 1.15 of the quality report, and the exact instructions in Appendix D.

**Doctor, 19 real prompts, 8 replies per prompt and arm** (`python ablate.py doctor --note-arm --samples 8`):

| | Control | Rule in the system prompt | Note in the player's notes |
| --- | --- | --- | --- |
| Voted the proven town player | 16 of 108 (14.8%) | 8 of 103 (7.8%) | **0 of 108 (0.0%)** |
| Compared with control | | p = 0.13 | p = 0.00002 |
| Voted the real mafia | 56 | 65 | 75 |

All 16 mistakes came from the two real blunder prompts. The rule fixed one of them (8 of 8 to 0 of 8) and not the other (8 of 8 to 8 of 8). The note fixed both. The note states the doctor's own conclusion as a fact ("you protected X on a night when nobody died, so X is NOT mafia"), so it does the inference for the model rather than teaching it.

**Villagers, 18 real prompts (from the second model's batch), 5 replies per prompt and arm** (`python ablate.py villager --model gemini-3.1-flash-lite --samples 5 --max-cases 18 --judge-model gemini-3.8-flash --judge-pairs 18`):

| | Control | Hint | p |
| --- | --- | --- | --- |
| Votes cast, abstained | 66, 24 | 78, 12 | |
| Reason rests on concrete evidence (text pattern) | 59.1% | 53.8% | 0.61 |
| Reason invents a vote record | 0.0% | 0.0% | 1.0 |
| Vote hits the real mafia | 57.6% | 50.0% | 0.40 |

Blind pairwise judge, 14 pairs: hint better 7, control better 0, ties 7 (sign test p = 0.016), no invented facts flagged in either arm. Four prompts could not be compared because the control arm always abstained. A text pattern sees no gain, but a judge that reads the replies preferred the hint every time it could decide, and the hint halved abstentions.

**Problems and fixes:**
* The runner crashed on the first villager prompt, because a progress line assumed a `blocked` field that only doctor cases have. It resumed from the saved result, and a regression test now runs the experiment on villager cases.
* A test wrote its output to the same file name as the batch summary it had just created. Renamed.
* Two statistics tests failed on floating point noise (0.9999999999999999 against 1.0, and a Wilson bound of -1e-17). The bound is now clamped to the range 0 to 1, and the other test compares approximately.
* An earlier look at the doctor hint alone reported "halved the mistake" (14.8% to 7.8%). Looking per prompt showed it fixed one of two, so the report states the per prompt result.

**Not done, and decisions pending:**
* Neither fix is built into the game. The doctor note is the strongest candidate. Adopting it means computing the note in the engine from the doctor's own protections and quiet nights, and then confirming in a fresh batch that "doctor voted a provably town player" drops to 0 and nothing else changes.
* The villager hint needs a full batch rated by the primary judge. A replay of single decisions cannot show a change in game quality.

---

## Open questions and next experiments

0. **Adopt and confirm the doctor note.** In replay it removed the mistake (16 of 108 to 0 of 108). Build it into the doctor's prompt, then run a batch and check the hard check and that nothing else changes.
0. **Confirm the villager hint in full games.** Run a batch with it and have the primary judge rate it, looking at whether the share of villager decisions rated sound moves from about 20%, and whether abstentions and vote accuracy change.

1. **Names or seats?** Rerun `batch_shuffle`'s seeds with the new names and `--no-cache`, and compare against `batch_shuffle` (see the names entry above). A stronger version randomizes names and seat order per game.
2. **More games.** 10 games per condition cannot settle balance. A town win rate of 6 of 10 has a plausible range of roughly 30% to 85%.
3. **Two mafia at 6 players.** Test `--mafia 2` now that the prompts and the shuffle are in place.
4. **Memory between games.** Per opponent notes written after each game and used in the next. Not started.
5. **Mafia adaptation.** The mafia retried a blocked target on 2 of 6 blocked nights in the baseline. Check whether this changes with more games.
