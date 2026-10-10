# Batch quality report

10 finished games, 6 players, model `gemini-3.1-flash-lite`, seeds from 100.

## Games

| Seed | Winner | Days | Calls | Tokens | Invalid | Minutes | Power roles alive at end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | town | 2 | 36 | 48,069 | 0 | 6.5 | doctor, detective |
| 101 | town | 2 | 36 | 48,623 | 0 | 6.6 | detective |
| 102 | town | 2 | 32 | 43,469 | 0 | 5.5 | detective |
| 103 | mafia | 2 | 30 | 38,386 | 0 | 5.3 | doctor |
| 104 | town | 1 | 18 | 17,657 | 0 | 4.3 | doctor |
| 105 | mafia | 3 | 49 | 82,263 | 0 | 10.6 | none |
| 106 | mafia | 3 | 38 | 54,632 | 0 | 5.5 | doctor |
| 107 | town | 1 | 21 | 22,384 | 0 | 2.7 | doctor, detective |
| 108 | town | 1 | 18 | 17,884 | 0 | 2.8 | doctor, detective |
| 109 | town | 2 | 36 | 50,597 | 0 | 4.6 | detective |

## Reliability and cost

| Metric | Value | How to read it |
| --- | --- | --- |
| Games finished | 10 of 10 | Failed games are excluded from everything below. |
| Invalid actions | 0 | Replies the engine could not use. It retried, then used a safe default. |
| API errors | 0 | Failed model calls. |
| Fallback speeches | 0 | Times a player said nothing because every retry failed. |
| Model calls per game | 31.4 | Free tier budget per game. |
| Tokens per game | 42,396 | Prompt plus reply tokens. |
| Minutes per game | 5.4 | At the configured request rate. |

## Information leak audit

| Metric | Value | How to read it |
| --- | --- | --- |
| Games audited | 10 (0 skipped, no prompt trace) | Needs the saved prompts in trace files. |
| Prompts checked | 315 | Every prompt sent to a player. |
| History lines checked | 6,756 | Each must be an event that player was allowed to see. |
| Leaks | 0 | A line of history the player should not have seen. Must be 0. |
| Role mismatches | 0 | The role in the prompt differs from the real role. Must be 0. |
| Teammate mismatches | 0 | The fellow mafia list is wrong. Must be 0. |

## Reasoning quality (hard checks)

| Metric | Value | How to read it |
| --- | --- | --- |
| Doctor voted for a player their own protection had shown to be town | 0 of 6 | A blocked kill means the mafia aimed at that player, so they cannot be mafia. Voting them out ignores what the doctor knows. Should be 0. |
| Detective voted for a player they had cleared | 0 of 10 | Ignoring their own result. Should be 0. |
| Detective voted for a mafia they had found | 3 of 3 | Acting on their own result. Higher is better. |
| Mafia voted for their own partner | 0 of 18 | Rarely a good idea. |
| Statements about the public record that were false | 0 of 6 (0.0%) | Claims about who voted for whom, who died and how, who claimed a role, or who a dead player was. Mafia lying about themselves is not counted. |
| Vote reasoning names the player voted for | 94.6% of 74 | Whether the private reasoning behind a vote is about the person actually voted for. |
| What votes rest on: a claim, a vote record, a night result, or an inconsistency | 58.1% | Concrete evidence cited in the reasoning. |
| What votes rest on: behavior only | 29.7% | Defensive, evasive, quiet, and similar. Weaker, but all there is on day 1. |
| What votes rest on: nothing specific | 12.2% | No reason that points at anything. |
| Town followed a true detective claim | 3 of 3 | A true claim should get more votes on the accused than on the claimant. |
| Town followed a false detective claim | 0 of 1 | A false claim (mafia counterclaim, or invented result) that the town believed. Lower is better. |

## Judge review

128 decisions in 10 games were rated by `gemini-3.6-flash` (0 games could not be rated). The judge saw every secret role and private reasoning, but rated each decision only against what that player knew at the time. Sound means a competent player could reasonably decide this. Weak means thin evidence or an overlooked clue. Illogical means it contradicts something the player knew or a false fact.

| Decisions | Count | Sound | Weak | Illogical |
| --- | --- | --- | --- | --- |
| All | 128 | 68.8% | 29.7% | 1.6% |
| Vote | 74 | 47.3% | 51.4% | 1.4% |
| Protect | 19 | 94.7% | 0.0% | 5.3% |
| Check | 16 | 100.0% | 0.0% | 0.0% |
| Mafia kill | 19 | 100.0% | 0.0% | 0.0% |
| By role: villager | 33 | 27.3% | 72.7% | 0.0% |
| By role: doctor | 30 | 66.7% | 30.0% | 3.3% |
| By role: detective | 28 | 82.1% | 17.9% | 0.0% |
| By role: mafia | 37 | 97.3% | 0.0% | 2.7% |

Overall logic of the game, scored 1 to 5 by the judge: **3.2** on average.

**Checking the judge against the hard checks.** These votes can be settled mechanically, so they act as an answer key:

* Votes where the detective acted on a mafia they had found: the judge rated 3 of 3 as sound.

Why decisions were not rated sound: unsupported accusation (37), ignored private knowledge (2), factual error (1).

### Decisions the judge rated illogical

* game 074097 day 1, Flo (doctor), protect Bob: Flo falsely claims Bob was vocal before Night 1, despite no discussion having taken place yet.
* game 074097 day 1, Ann (mafia), vote Bob: Ann's private reasoning claims Bob is lying and framing her, contradicting her own private knowledge that she is mafia.

## Outcomes (not a quality measure)

| Metric | Value | How to read it |
| --- | --- | --- |
| Town wins | 7 of 10 | A win can come from bad reasoning and a loss from good reasoning. Small sample. |
| Mafia wins | 3 of 10 |  |
| Average days | 1.9 | Very short games mean luck decided them. |
| Ejections that hit mafia | 7 of 17 | How often the daily vote found the mafia. |
| Power roles ejected by town | 3 | Town voting out its own doctor or detective. |
| Days with no ejection | 1 | Ties or all abstentions. |

## Deduction and voting

| Metric | Value | How to read it |
| --- | --- | --- |
| Town vote accuracy | 42.9% | Share of town votes that targeted a mafia player. |
| Random guessing baseline | 27.1% | What random voting would score in the same situations. Accuracy above this means real deduction. |
| Town abstentions | 18.8% | Votes cast for nobody. |
| Mafia votes for their own partner | 0 | Bussing. Usually a strategic sacrifice or a mistake. |

## Role play and information control

| Metric | Value | How to read it |
| --- | --- | --- |
| Games where the doctor outed themself | 0 of 10 | Public speech that reveals the protection. Ideally rare and deliberate. |
| Games where the detective claimed | 6 of 10 | Detective speech that reveals investigations. |
| Fake power role claims | 1 | Speeches by mafia or villagers claiming to be the doctor or detective. |
| Mafia speaking as mafia in public | 0 | Should be near zero. Flagged phrases may include accusations, so read the examples. |
| Detective found a mafia | 4 |  |
| Detective reported it later | 75.0% | Named the found mafia in a later public speech. Low means the result was wasted. |
| Mafia kills aimed at power roles | 31.6% | Random targeting would hit a power role 2 in 5 times with 6 players. |
| Kills stopped by the doctor | 7 of 19 |  |
| Doctor protected themself | 0.0% |  |
| Doctor repeated the same target | 4 | Nights the doctor picked the same person as the night before. |
| Mafia retried a saved target | 3 | Nights the mafia hit the same person right after being blocked. |
| Mafia disagreements on the target | 0 | Rounds of kill voting that split. |

## Choice bias

| Metric | Value | How to read it |
| --- | --- | --- |
| Mafia kill target: first name listed in the prompt | 57.9% of 19 (chance 24.6%) | Far above chance means the model leans on list position. Needs the saved prompt trace. |
| Mafia kill target: earliest seat (first in the roster) | 52.6% of 19 (chance 24.6%) | Far above chance means a preference for certain names, whatever the list order. |
| Doctor protection: first name listed in the prompt | 21.1% of 19 (chance 19.5%) |  |
| Doctor protection: earliest seat (first in the roster) | 52.6% of 19 (chance 19.5%) |  |
| Detective check: first name listed in the prompt | 18.8% of 16 (chance 22.4%) |  |
| Detective check: earliest seat (first in the roster) | 68.8% of 16 (chance 22.4%) |  |
| Day vote: first name listed in the prompt | 29.7% of 74 (chance 27.4%) |  |
| Day vote: earliest seat (first in the roster) | 18.9% of 74 (chance 27.4%) |  |

## Writing quality

| Metric | Value | How to read it |
| --- | --- | --- |
| Average speech length | 183.4 characters |  |
| Very short speeches | 0.0% | Under 25 characters. |
| Agree with the last speaker | 8.6% | Speeches with phrases like good point or I agree. High means players echo each other. |
| Near duplicate speeches | 0.0% | Share of speeches that are 60 percent or more similar to another in the same game. |
| Word pair variety | 0.879 | Distinct two word pairs over all pairs. Closer to 1 is more varied. |
| Most common opening | 7.7% | Share of speeches starting with the same three words. |
| Format leaks | 0 | Speeches showing JSON or log tags. Should be zero. |
| Invented history on day 1 | 1 | Speeches on day 1 that mention yesterday or earlier rounds. |

## Logic problems found


### Reasoning about one player, vote for another

* game 071445 day 2, Flo (doctor): voted Cy, but the reasoning never mentions them: "I trust the detective's investigation; leaving a confirmed mafia player alive is too dangerous."
* game 071834 day 2, Ann (villager): voted Bob, but the reasoning never mentions them: "Di has claimed the detective role and cleared me and Flo. Given we are at a critical stage, I will trust the investigative result to avoid a mafia victory."
* game 072228 day 2, Ed (villager): voted Cy, but the reasoning never mentions them: "Di has claimed detective and the alternative is to ignore the only lead we have after losing our doctor. I will trust the detective's investigation."
* game 074423 day 1, Cy (villager): voted Ann, but the reasoning never mentions them: "The entire group is fixating on a single, non-incriminating comment I made. This level of synchronized pressure from everyone suggests a coordinated effort by t"

### How the town handled detective claims

* game 071445 day 2, Ann (detective): true claim against Cy: 2 votes on the accused, 0 on the claimant
* game 074097 day 1, Bob (detective): true claim against Ann: 1 votes on the accused, 0 on the claimant
* game 074423 day 2, Flo (detective): true claim against Bob: 2 votes on the accused, 0 on the claimant
* game 074423 day 2, Bob (mafia): false claim against Flo: 0 votes on the accused, 2 on the claimant

## Examples


### Power role claims by the real holder

* game 071445 day 2, Ann (detective): "I am the detective. I investigated Cy last night and he is mafia. We must vote Cy out now."
* game 071445 day 2, Ann (detective): "Cy, your deflection is expected. My investigation is definitive: you are mafia, and the town needs to act now."
* game 071834 day 2, Di (detective): "Bob, my investigations are not matters of convenience but the primary evidence we have left. Given that I have cleared Ann and Flo, you are the only remaining individual I have not investigated, and your defensive deflection is telling."
* game 072228 day 2, Di (detective): "I must disclose that I am the detective; my investigations into Ann and Ed have confirmed that both are not mafia. Consequently, Cy is the only remaining individual I have not cleared, and I believe we should focus our efforts there."
* game 072228 day 2, Di (detective): "My role as detective is verifiable through the process of elimination; if I were mafia, I would not be narrowing down the pool to the only remaining suspect so transparently. Cy, if you are not the mafia, you must provide a logical reason w"
* game 073133 day 1, Ed (detective): "I am the detective and I investigated Ann last night. I only shared the result to help the town, and my early slip-up was an attempt to provide information."

### Fake power role claims

* game 074423 day 2, Bob (mafia): "That is an astonishing fabrication, Flo; I am the actual detective, and my investigation last night confirmed that you are the mafia. It seems you are attempting a desperate gambit to eliminate the person who uncovered your true identity."

### Invented history

* game 072876 day 1, Ed (doctor): "Losing the detective so early is a disaster, but we can't let panic dictate our actions. Who has any reason to target Bob specifically, and why are we so quiet about yesterday's interactions?"

### Agreeing with the last speaker

* game 071445 day 1, Cy (mafia): "It's definitely a relief to see everyone still here! I agree with Flo—let's keep a close eye on the people who haven't contributed much to the conversation yet."
* game 071445 day 1, Ann (detective): "I agree that we should watch for suspicious behavior. Bob seems to be contributing well, so I'm not focused on him yet."
* game 071445 day 1, Ed (villager): "It is great that we all made it through the night! I agree that we should be observant, but let's be careful not to jump to conclusions about people who are just being thoughtful and taking their time."
* game 071445 day 1, Bob (villager): "Di makes a fair point. If we all agree too quickly, the mafia can easily hide among us. Ed, why are you so worried about us being suspicious of the quiet ones?"
* game 072228 day 1, Di (detective): "The loss of Bob is indeed regrettable, but I agree with Ann that it is too early to draw definitive conclusions. I shall observe the discourse today to see if anyone's contributions appear intentionally diversionary."
* game 072228 day 1, Cy (mafia): "Di makes a great point about watching for diversionary tactics. Since we're all just feeling things out, maybe we can each share who we think is being the most helpful so far?"
