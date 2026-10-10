# Batch quality report

10 finished games, 6 players, model `gemini-3.5-flash-lite`, seeds from 100.

## Games

| Seed | Winner | Days | Calls | Tokens | Invalid | Minutes | Power roles alive at end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | mafia | 3 | 36 | 49,363 | 0 | 3.5 | none |
| 101 | town | 2 | 36 | 48,694 | 0 | 3.5 | doctor, detective |
| 102 | town | 3 | 59 | 113,734 | 0 | 5.8 | doctor, detective |
| 103 | town | 1 | 18 | 17,435 | 0 | 1.7 | doctor |
| 104 | mafia | 3 | 49 | 81,538 | 0 | 4.8 | none |
| 105 | mafia | 3 | 43 | 67,394 | 0 | 5.2 | doctor |
| 106 | town | 2 | 32 | 44,044 | 0 | 3.2 | doctor, detective |
| 107 | mafia | 3 | 34 | 44,755 | 0 | 3.3 | none |
| 108 | town | 2 | 36 | 47,049 | 0 | 3.5 | doctor, detective |
| 109 | town | 2 | 33 | 45,364 | 0 | 3.2 | doctor, detective |

## Reliability and cost

| Metric | Value | How to read it |
| --- | --- | --- |
| Games finished | 10 of 10 | Failed games are excluded from everything below. |
| Invalid actions | 0 | Replies the engine could not use. It retried, then used a safe default. |
| API errors | 0 | Failed model calls. |
| Fallback speeches | 0 | Times a player said nothing because every retry failed. |
| Model calls per game | 37.6 | Free tier budget per game. |
| Tokens per game | 55,937 | Prompt plus reply tokens. |
| Minutes per game | 3.8 | At the configured request rate. |

## Information leak audit

| Metric | Value | How to read it |
| --- | --- | --- |
| Games audited | 10 (0 skipped, no prompt trace) | Needs the saved prompts in trace files. |
| Prompts checked | 378 | Every prompt sent to a player. |
| History lines checked | 9,745 | Each must be an event that player was allowed to see. |
| Leaks | 0 | A line of history the player should not have seen. Must be 0. |
| Role mismatches | 0 | The role in the prompt differs from the real role. Must be 0. |
| Teammate mismatches | 0 | The fellow mafia list is wrong. Must be 0. |

## Reasoning quality (hard checks)

| Metric | Value | How to read it |
| --- | --- | --- |
| Doctor voted for a player their own protection had shown to be town | 2 of 9 | A blocked kill means the mafia aimed at that player, so they cannot be mafia. Voting them out ignores what the doctor knows. Should be 0. |
| Detective voted for a player they had cleared | 0 of 8 | Ignoring their own result. Should be 0. |
| Detective voted for a mafia they had found | 4 of 4 | Acting on their own result. Higher is better. |
| Mafia voted for their own partner | 0 of 19 | Rarely a good idea. |
| Statements about the public record that were false | 0 of 13 (0.0%) | Claims about who voted for whom, who died and how, who claimed a role, or who a dead player was. Mafia lying about themselves is not counted. |
| Vote reasoning names the player voted for | 100.0% of 82 | Whether the private reasoning behind a vote is about the person actually voted for. |
| What votes rest on: a claim, a vote record, a night result, or an inconsistency | 68.3% | Concrete evidence cited in the reasoning. |
| What votes rest on: behavior only | 22.0% | Defensive, evasive, quiet, and similar. Weaker, but all there is on day 1. |
| What votes rest on: nothing specific | 9.8% | No reason that points at anything. |
| Town followed a true detective claim | 4 of 4 | A true claim should get more votes on the accused than on the claimant. |
| Town followed a false detective claim | 0 of 1 | A false claim (mafia counterclaim, or invented result) that the town believed. Lower is better. |

## Judge review

145 decisions in 10 games were rated by `gemini-3.6-flash` (0 games could not be rated). The judge saw every secret role and private reasoning, but rated each decision only against what that player knew at the time. Sound means a competent player could reasonably decide this. Weak means thin evidence or an overlooked clue. Illogical means it contradicts something the player knew or a false fact.

| Decisions | Count | Sound | Weak | Illogical |
| --- | --- | --- | --- | --- |
| All | 145 | 69.7% | 29.0% | 1.4% |
| Vote | 82 | 46.3% | 51.2% | 2.4% |
| Protect | 22 | 100.0% | 0.0% | 0.0% |
| Check | 17 | 100.0% | 0.0% | 0.0% |
| Mafia kill | 24 | 100.0% | 0.0% | 0.0% |
| By role: villager | 36 | 22.2% | 77.8% | 0.0% |
| By role: doctor | 37 | 75.7% | 18.9% | 5.4% |
| By role: detective | 29 | 75.9% | 24.1% | 0.0% |
| By role: mafia | 43 | 100.0% | 0.0% | 0.0% |

Overall logic of the game, scored 1 to 5 by the judge: **2.8** on average.

**Checking the judge against the hard checks.** These votes can be settled mechanically, so they act as an answer key:

* Votes that contradicted what the voter knew: the judge rated 2 of 2 as weak or illogical (2 as illogical).
* Votes where the detective acted on a mafia they had found: the judge rated 4 of 4 as sound.

Why decisions were not rated sound: unsupported accusation (36), ignored public evidence (5), ignored private knowledge (3).

### Decisions the judge rated illogical

* game 070298 day 3, Bob (doctor), vote Cy: Bob protected Cy during two consecutive no-kill nights, proving Cy innocent, yet Bob voted to eject Cy.
* game 070805 day 2, Flo (doctor), vote Di: Flo saved Di on Night 2, proving Di is innocent, making voting for Di illogical.

## Outcomes (not a quality measure)

| Metric | Value | How to read it |
| --- | --- | --- |
| Town wins | 6 of 10 | A win can come from bad reasoning and a loss from good reasoning. Small sample. |
| Mafia wins | 4 of 10 |  |
| Average days | 2.4 | Very short games mean luck decided them. |
| Ejections that hit mafia | 6 of 18 | How often the daily vote found the mafia. |
| Power roles ejected by town | 3 | Town voting out its own doctor or detective. |
| Days with no ejection | 4 | Ties or all abstentions. |

## Deduction and voting

| Metric | Value | How to read it |
| --- | --- | --- |
| Town vote accuracy | 46.0% | Share of town votes that targeted a mafia player. |
| Random guessing baseline | 28.0% | What random voting would score in the same situations. Accuracy above this means real deduction. |
| Town abstentions | 24.1% | Votes cast for nobody. |
| Mafia votes for their own partner | 0 | Bussing. Usually a strategic sacrifice or a mistake. |

## Role play and information control

| Metric | Value | How to read it |
| --- | --- | --- |
| Games where the doctor outed themself | 0 of 10 | Public speech that reveals the protection. Ideally rare and deliberate. |
| Games where the detective claimed | 5 of 10 | Detective speech that reveals investigations. |
| Fake power role claims | 1 | Speeches by mafia or villagers claiming to be the doctor or detective. |
| Mafia speaking as mafia in public | 1 | Should be near zero. Flagged phrases may include accusations, so read the examples. |
| Detective found a mafia | 7 |  |
| Detective reported it later | 57.1% | Named the found mafia in a later public speech. Low means the result was wasted. |
| Mafia kills aimed at power roles | 37.5% | Random targeting would hit a power role 2 in 5 times with 6 players. |
| Kills stopped by the doctor | 11 of 24 |  |
| Doctor protected themself | 4.5% |  |
| Doctor repeated the same target | 5 | Nights the doctor picked the same person as the night before. |
| Mafia retried a saved target | 4 | Nights the mafia hit the same person right after being blocked. |
| Mafia disagreements on the target | 0 | Rounds of kill voting that split. |

## Choice bias

| Metric | Value | How to read it |
| --- | --- | --- |
| Mafia kill target: first name listed in the prompt | 33.3% of 24 (chance 27.1%) | Far above chance means the model leans on list position. Needs the saved prompt trace. |
| Mafia kill target: earliest seat (first in the roster) | 37.5% of 24 (chance 27.1%) | Far above chance means a preference for certain names, whatever the list order. |
| Doctor protection: first name listed in the prompt | 13.6% of 22 (chance 20.2%) |  |
| Doctor protection: earliest seat (first in the roster) | 36.4% of 22 (chance 20.2%) |  |
| Detective check: first name listed in the prompt | 29.4% of 17 (chance 22.2%) |  |
| Detective check: earliest seat (first in the roster) | 47.1% of 17 (chance 22.2%) |  |
| Day vote: first name listed in the prompt | 31.7% of 82 (chance 28.3%) |  |
| Day vote: earliest seat (first in the roster) | 23.2% of 82 (chance 28.3%) |  |

## Writing quality

| Metric | Value | How to read it |
| --- | --- | --- |
| Average speech length | 188.1 characters |  |
| Very short speeches | 0.0% | Under 25 characters. |
| Agree with the last speaker | 5.2% | Speeches with phrases like good point or I agree. High means players echo each other. |
| Near duplicate speeches | 0.0% | Share of speeches that are 60 percent or more similar to another in the same game. |
| Word pair variety | 0.896 | Distinct two word pairs over all pairs. Closer to 1 is more varied. |
| Most common opening | 5.6% | Share of speeches starting with the same three words. |
| Format leaks | 0 | Speeches showing JSON or log tags. Should be zero. |
| Invented history on day 1 | 0 | Speeches on day 1 that mention yesterday or earlier rounds. |

## Logic problems found


### Doctor ignored what their protection showed

* game 070298 day 3, Bob (doctor): voted Cy, whom their own protection had just shown to be the mafia's target: "Cy has consistently driven the major bandwagons, including the detective lynch on day one, and is now deflecting under pressure."
* game 070805 day 2, Flo (doctor): voted Di, whom their own protection had just shown to be the mafia's target: "Di is aggressively pushing a narrative against yesterday's voters despite Cy's town-losing evasiveness, deflecting blame."

### How the town handled detective claims

* game 069348 day 2, Di (detective): true claim against Bob: 3 votes on the accused, 0 on the claimant
* game 069559 day 3, Di (detective): true claim against Cy: 3 votes on the accused, 0 on the claimant
* game 069559 day 3, Cy (mafia): false claim against Di: 0 votes on the accused, 3 on the claimant
* game 071005 day 2, Cy (detective): true claim against Ed: 2 votes on the accused, 0 on the claimant
* game 071216 day 2, Flo (detective): true claim against Bob: 2 votes on the accused, 0 on the claimant

## Examples


### Power role claims by the real holder

* game 069136 day 1, Ann (detective): "Bob is clear. I investigated him last night and he is not mafia."
* game 069348 day 1, Di (detective): "Ann stated, 'let's pay close attention to how everyone reacts and votes today rather than rushing to conclusions.' While caution is warranted, I note that Ann's calm demeanor could be analyzed further, though my investigation on her last ni"
* game 069348 day 1, Di (detective): "Flo suggests my revelation is 'too convenient,' but withholding a verified non-mafia result on Ann would actively harm town progress. As I stated, my investigation on Ann returned a negative for mafia affiliation, leaving Bob and Ed as the "
* game 069348 day 2, Di (detective): "Bob remarked, 'doesn't it seem awfully convenient that the doctor's protection landed precisely where Di needed it'. My investigation last night on Bob confirmed that he is indeed mafia, which explains his persistent attempts to discredit m"
* game 069348 day 2, Di (detective): "Bob attempts to dismiss my findings as retaliation, but my investigation yielded a definitive mafia result. Bob's frantic denials only confirm his guilt, and town must eliminate him today."
* game 069559 day 3, Di (detective): "I must formally announce my role as the Detective, for I have investigated Cy and found Cy to be mafia. Given that Cy and Bob traded votes yesterday and Bob was murdered tonight, this evidence is definitive."

### Fake power role claims

* game 069559 day 3, Cy (mafia): "That is an absolute lie, Di! I am actually the detective, and I investigated Di last night and found Di to be mafia; this is a desperate last-second counterclaim to save their own skin."

### Mafia speaking as mafia

* game 069559 day 3, Cy (mafia): "Di's claim only came out because I pinned them as mafia with my detective investigation first! Don't let a fast counterclaim blind you to the fact that Di is fabricating this to protect themselves."

### Agreeing with the last speaker

* game 069136 day 2, Ed (villager): "Bob makes a very fair point about Di voting for Ann as well while trying to act completely blameless today. Di, you can't pretend you weren't right there driving the wagon with the rest of us!"
* game 069559 day 1, Cy (mafia): "Hello everyone! I completely agree with Bob and Ed—jumping to conclusions today would be a bit silly without any leads. Let's keep our minds open and just enjoy a calm, observant discussion for now."
* game 069559 day 1, Flo (doctor): "bob makes a fair point about everyone agreeing too fast, but on day 1 being cautious isn't automatically stalling. let's not manufacture pressure where there isn't any yet."
* game 069559 day 1, Cy (mafia): "That's a really fair point by Bob to keep us on our toes, but Ed and Flo are right that we shouldn't manufacture pressure when there's literally no data yet. Let's keep looking at how people naturally interact instead!"
* game 070009 day 1, Bob (detective): "I completely agree that we shouldn't rush into any blind lynches today! Let's watch who tries to manufacture quick bandwagons out of thin air."
* game 070009 day 2, Ann (villager): "Flo makes a fair point that driving a lynch against the detective on Day 1 is almost too blatant for a mafia member. Let's not let Ed rush us into a retaliatory lynch against Flo without considering other angles."
