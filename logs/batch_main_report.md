# Batch quality report

10 finished games, 6 players, model `gemini-3.5-flash-lite`, seeds from 100.

## Games

| Seed | Winner | Days | Calls | Tokens | Invalid | Minutes | Power roles alive at end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | town | 1 | 18 | 17,699 | 0 | 1.7 | doctor, detective |
| 101 | mafia | 3 | 36 | 47,465 | 0 | 3.5 | none |
| 102 | town | 2 | 32 | 43,836 | 0 | 3.1 | doctor, detective |
| 103 | town | 2 | 33 | 42,982 | 0 | 3.2 | doctor, detective |
| 104 | town | 1 | 20 | 21,239 | 0 | 2.1 | doctor, detective |
| 105 | town | 2 | 28 | 34,767 | 0 | 2.7 | none |
| 106 | town | 1 | 18 | 18,034 | 0 | 1.7 | doctor, detective |
| 107 | town | 3 | 56 | 100,870 | 0 | 5.6 | doctor |
| 108 | town | 2 | 35 | 46,741 | 0 | 3.4 | none |
| 109 | town | 1 | 4 | 5,669 | 0 | 0.3 | doctor, detective |

## Reliability and cost

| Metric | Value | How to read it |
| --- | --- | --- |
| Games finished | 10 of 10 | Failed games are excluded from everything below. |
| Invalid actions | 0 | Replies the engine could not use. It retried, then used a safe default. |
| API errors | 0 | Failed model calls. |
| Fallback speeches | 0 | Times a player said nothing because every retry failed. |
| Model calls per game | 28.0 | Free tier budget per game. |
| Tokens per game | 37,930 | Prompt plus reply tokens. |
| Minutes per game | 2.7 | At the configured request rate. |

## Information leak audit

| Metric | Value | How to read it |
| --- | --- | --- |
| Games audited | 10 (0 skipped, no prompt trace) | Needs the saved prompts in trace files. |
| Prompts checked | 299 | Every prompt sent to a player. |
| History lines checked | 6,330 | Each must be an event that player was allowed to see. |
| Leaks | 0 | A line of history the player should not have seen. Must be 0. |
| Role mismatches | 0 | The role in the prompt differs from the real role. Must be 0. |
| Teammate mismatches | 0 | The fellow mafia list is wrong. Must be 0. |

## Reasoning quality (hard checks)

| Metric | Value | How to read it |
| --- | --- | --- |
| Doctor voted for a player their own protection had shown to be town | 0 of 4 | A blocked kill means the mafia aimed at that player, so they cannot be mafia. Voting them out ignores what the doctor knows. Should be 0. |
| Detective voted for a player they had cleared | 0 of 7 | Ignoring their own result. Should be 0. |
| Detective voted for a mafia they had found | 4 of 4 | Acting on their own result. Higher is better. |
| Mafia voted for their own partner | 0 of 17 | Rarely a good idea. |
| Statements about the public record that were false | 0 of 6 (0.0%) | Claims about who voted for whom, who died and how, who claimed a role, or who a dead player was. Mafia lying about themselves is not counted. |
| Vote reasoning names the player voted for | 100.0% of 70 | Whether the private reasoning behind a vote is about the person actually voted for. |
| What votes rest on: a claim, a vote record, a night result, or an inconsistency | 60.0% | Concrete evidence cited in the reasoning. |
| What votes rest on: behavior only | 32.9% | Defensive, evasive, quiet, and similar. Weaker, but all there is on day 1. |
| What votes rest on: nothing specific | 7.1% | No reason that points at anything. |
| Town followed a true detective claim | 2 of 4 | A true claim should get more votes on the accused than on the claimant. |
| Town followed a false detective claim | 0 of 1 | A false claim (mafia counterclaim, or invented result) that the town believed. Lower is better. |

## Judge review

117 decisions in 10 games were rated by `gemini-3.6-flash` (0 games could not be rated). The judge saw every secret role and private reasoning, but rated each decision only against what that player knew at the time. Sound means a competent player could reasonably decide this. Weak means thin evidence or an overlooked clue. Illogical means it contradicts something the player knew or a false fact.

| Decisions | Count | Sound | Weak | Illogical |
| --- | --- | --- | --- | --- |
| All | 117 | 64.1% | 33.3% | 2.6% |
| Vote | 70 | 40.0% | 55.7% | 4.3% |
| Protect | 16 | 100.0% | 0.0% | 0.0% |
| Check | 13 | 100.0% | 0.0% | 0.0% |
| Mafia kill | 18 | 100.0% | 0.0% | 0.0% |
| By role: villager | 33 | 12.1% | 78.8% | 9.1% |
| By role: doctor | 26 | 73.1% | 26.9% | 0.0% |
| By role: detective | 23 | 78.3% | 21.7% | 0.0% |
| By role: mafia | 35 | 97.1% | 2.9% | 0.0% |

Overall logic of the game, scored 1 to 5 by the judge: **2.7** on average.

**Checking the judge against the hard checks.** These votes can be settled mechanically, so they act as an answer key:

* Votes where the detective acted on a mafia they had found: the judge rated 4 of 4 as sound.

Why decisions were not rated sound: unsupported accusation (37), factual error (2), contradicts own statements (1), ignored public evidence (1), bandwagon without reason (1).

### Decisions the judge rated illogical

* game 709569 day 1, Ann (villager), vote Di: Ann states that voting out a power role is too risky, yet proceed to vote to eject Di anyway.
* game 710286 day 2, Ann (villager), vote Di: Describing Ed's claim as dubious contradicts the public reveal that Ed was indeed the genuine detective.
* game 710885 day 2, Bob (villager), vote Ed: Bob falsely claims Ed led the charge against Cy when Bob himself instigated suspicion against Cy first.

## Outcomes (not a quality measure)

| Metric | Value | How to read it |
| --- | --- | --- |
| Town wins | 9 of 10 | A win can come from bad reasoning and a loss from good reasoning. Small sample. |
| Mafia wins | 1 of 10 |  |
| Average days | 1.8 | Very short games mean luck decided them. |
| Ejections that hit mafia | 9 of 15 | How often the daily vote found the mafia. |
| Power roles ejected by town | 5 | Town voting out its own doctor or detective. |
| Days with no ejection | 2 | Ties or all abstentions. |

## Deduction and voting

| Metric | Value | How to read it |
| --- | --- | --- |
| Town vote accuracy | 54.7% | Share of town votes that targeted a mafia player. |
| Random guessing baseline | 26.3% | What random voting would score in the same situations. Accuracy above this means real deduction. |
| Town abstentions | 20.9% | Votes cast for nobody. |
| Mafia votes for their own partner | 0 | Bussing. Usually a strategic sacrifice or a mistake. |

## Role play and information control

| Metric | Value | How to read it |
| --- | --- | --- |
| Games where the doctor outed themself | 0 of 10 | Public speech that reveals the protection. Ideally rare and deliberate. |
| Games where the detective claimed | 4 of 10 | Detective speech that reveals investigations. |
| Fake power role claims | 2 | Speeches by mafia or villagers claiming to be the doctor or detective. |
| Mafia speaking as mafia in public | 0 | Should be near zero. Flagged phrases may include accusations, so read the examples. |
| Detective found a mafia | 3 |  |
| Detective reported it later | 100.0% | Named the found mafia in a later public speech. Low means the result was wasted. |
| Mafia kills aimed at power roles | 22.2% | Random targeting would hit a power role 2 in 5 times with 6 players. |
| Kills stopped by the doctor | 7 of 18 |  |
| Doctor protected themself | 0.0% |  |
| Doctor repeated the same target | 2 | Nights the doctor picked the same person as the night before. |
| Mafia retried a saved target | 2 | Nights the mafia hit the same person right after being blocked. |
| Mafia disagreements on the target | 0 | Rounds of kill voting that split. |

## Choice bias

| Metric | Value | How to read it |
| --- | --- | --- |
| Mafia kill target: first name listed in the prompt | 55.6% of 18 (chance 24.3%) | Far above chance means the model leans on list position. Needs the saved prompt trace. |
| Mafia kill target: earliest seat (first in the roster) | 55.6% of 18 (chance 24.3%) | Far above chance means a preference for certain names, whatever the list order. |
| Doctor protection: first name listed in the prompt | 37.5% of 16 (chance 18.0%) |  |
| Doctor protection: earliest seat (first in the roster) | 37.5% of 16 (chance 18.0%) |  |
| Detective check: first name listed in the prompt | 84.6% of 13 (chance 21.4%) |  |
| Detective check: earliest seat (first in the roster) | 84.6% of 13 (chance 21.4%) |  |
| Day vote: first name listed in the prompt | 28.6% of 70 (chance 26.5%) |  |
| Day vote: earliest seat (first in the roster) | 28.6% of 70 (chance 26.5%) |  |

## Writing quality

| Metric | Value | How to read it |
| --- | --- | --- |
| Average speech length | 176.1 characters |  |
| Very short speeches | 0.0% | Under 25 characters. |
| Agree with the last speaker | 6.0% | Speeches with phrases like good point or I agree. High means players echo each other. |
| Near duplicate speeches | 0.0% | Share of speeches that are 60 percent or more similar to another in the same game. |
| Word pair variety | 0.896 | Distinct two word pairs over all pairs. Closer to 1 is more varied. |
| Most common opening | 8.8% | Share of speeches starting with the same three words. |
| Format leaks | 0 | Speeches showing JSON or log tags. Should be zero. |
| Invented history on day 1 | 1 | Speeches on day 1 that mention yesterday or earlier rounds. |

## Logic problems found


### How the town handled detective claims

* game 709780 day 2, Di (detective): true claim against Cy: 2 votes on the accused, 0 on the claimant
* game 709968 day 2, Cy (detective): true claim against Bob: 2 votes on the accused, 0 on the claimant
* game 709968 day 2, Bob (mafia): false claim against Cy: 0 votes on the accused, 2 on the claimant
* game 710552 day 1, Bob (detective): true claim against Ann: 0 votes on the accused, 0 on the claimant
* game 710552 day 2, Bob (detective): true claim against Ann: 0 votes on the accused, 3 on the claimant

## Examples


### Power role claims by the real holder

* game 709569 day 1, Di (detective): "Since nobody perished last night, the doctor made a successful intervention. I note that Ann has been cleared through my investigation, so we should direct our scrutiny elsewhere."
* game 709780 day 2, Di (detective): "Cy, your overly pleasant greeting cannot mask the truth. I am the detective, and I investigated you last night: you are mafia."
* game 709780 day 2, Di (detective): "Cy, claiming you are being framed does not override concrete evidence; I investigated you last night and you are definitively mafia."
* game 709968 day 2, Cy (detective): "I am the detective, and I investigated Bob last night. He is mafia, plain and simple, and we need to vote him out right now."
* game 709968 day 2, Cy (detective): "Bob is lying through his teeth with a textbook desperate mafia counterclaim. I am the real detective, my result on him is solid, and we cannot let him survive this day."
* game 710552 day 1, Bob (detective): "I am the detective, and I investigated Ann last night. She came up as Mafia, so we need to vote her out right now."

### Fake power role claims

* game 709968 day 2, Bob (mafia): "Well, that's a neat little fairy tale, Cy, especially since *I* am the actual detective and my investigation last night pointed squarely at Cy. Voting me out based on a desperate counterclaim would be a massive gift to the remaining mafia."
* game 709968 day 2, Bob (mafia): "I investigated Ann on night one before she tragically bit the dust, and Cy is just thrashing around trying to eliminate the actual cop. If you hang me today, you're handing the game to Cy on a silver platter."

### Invented history

* game 710552 day 1, Flo (doctor): "Well, a quiet night means the neighborhood watch is either competent or the criminals are still sleeping off yesterday's espresso. Let's not spend the whole day congratulating ourselves on surviving the obvious."

### Agreeing with the last speaker

* game 709467 day 1, Ed (villager): "Hello everyone! I agree we shouldn't get too bogged down in policing each other's emotional reactions so early. Let's take a deep breath and calmly look at who might be trying to push the conversation away from finding clues."
* game 709467 day 1, Cy (mafia): "Ed makes a solid point about not getting bogged down, but let's not just sit around taking deep breaths while the mafia runs free! Who here is actually ready to name a top suspect instead of dodging?"
* game 709780 day 1, Di (detective): "Bob raises a fair point that inaction is dangerous, yet Ed is correct that artificial panic creates poor reads. Let us examine everyone's underlying logic rather than trading jabs over pacing."
* game 709968 day 1, Flo (villager): "Cy makes a great point—we can't just shrug off Ann's death and chat about the weather! Let's poke around and see who is playing it a *little* too cool today."
* game 710162 day 1, Bob (detective): "Hey everyone, I'm fully here and listening! While Ann makes a solid point about keeping the conversation active, let's not get too bogged down arguing over who is talking too much or too little—we need to look closer at actual behavior!"
* game 710286 day 1, Ann (villager): "It really is heartbreaking to lose Bob right away before we even got to know him. Flo makes a good point about how lucky the mafia got, but let's keep our eyes open for anyone trying to steer us off the scent too quickly today."
