import pytest

from mafia.logic import logic_game, logic_rates

ROLES = {"Ann": "mafia", "Bob": "detective", "Cy": "doctor", "Di": "villager", "Ed": "villager", "Flo": "villager"}


def ev(kind, day=1, phase="day", text="", **data):
    return {"idx": 0, "day": day, "phase": phase, "kind": kind, "text": text, "data": data, "visible_to": None}


def game(*events):
    return [ev("setup", 0, "night", roles=ROLES, players=list(ROLES)), *events]


def counts(*events):
    return logic_game(game(*events))["counts"]


def blocked_night(day=1):
    """The mafia aimed at Di, the doctor protected Di, and nobody died: Di is provably not mafia."""
    return [ev("kill_decision", day, "night", target="Di"), ev("save", day, "night", actor="Cy", target="Di"), ev("no_death", day)]


def test_doctor_voting_for_the_player_their_protection_just_showed_is_town():
    c = counts(*blocked_night(), ev("thought", speaker="Cy", thought="Di seems deflecting"),
               ev("vote", voter="Cy", target="Di"), ev("vote", voter="Ed", target="Ann"))
    assert c["doctor_vote_opportunities"] == 1 and c["doctor_voted_saved_target"] == 1


def test_doctor_voting_for_someone_else_is_fine_and_a_kill_that_went_through_proves_nothing():
    c = counts(*blocked_night(), ev("vote", voter="Cy", target="Ann"))
    assert c["doctor_vote_opportunities"] == 1 and c.get("doctor_voted_saved_target", 0) == 0
    # the kill landed, so the saved player might simply have been a different person
    c = counts(ev("kill_decision", 1, "night", target="Di"), ev("save", 1, "night", actor="Cy", target="Ed"),
               ev("death", 1, victim="Di", role="villager", cause="night"), ev("vote", voter="Cy", target="Ed"))
    assert c.get("doctor_vote_opportunities", 0) == 0


def test_detective_votes_against_cleared_players_and_for_found_mafia():
    c = counts(ev("investigate", 1, "night", actor="Bob", target="Di", result="not mafia"),
               ev("investigate", 2, "night", actor="Bob", target="Ann", result="MAFIA"),
               ev("vote", 2, voter="Bob", target="Di"))            # cleared Di, and ignored the mafia he found
    assert c["detective_voted_cleared"] == 1 and c["detective_vote_opportunities"] == 1
    assert c["detective_found_vote_opportunities"] == 1 and c.get("detective_voted_found_mafia", 0) == 0
    c = counts(ev("investigate", 1, "night", actor="Bob", target="Ann", result="MAFIA"), ev("vote", voter="Bob", target="Ann"))
    assert c["detective_voted_found_mafia"] == 1


def test_mafia_voting_for_their_partner_needs_two_mafia():
    roles = dict(ROLES, Flo="mafia")
    events = [ev("setup", 0, "night", roles=roles, players=list(roles)), ev("vote", voter="Ann", target="Flo")]
    assert logic_game(events)["counts"]["mafia_voted_partner"] == 1


def test_vote_reasons_must_name_the_target_and_are_classified_by_basis():
    c = counts(
        ev("thought", speaker="Di", thought="Ed is deflecting and acting defensive."), ev("vote", voter="Di", target="Ed"),
        ev("thought", speaker="Ed", thought="Flo voted against the detective yesterday, a bandwagon."), ev("vote", voter="Ed", target="Flo"),
        ev("thought", speaker="Flo", thought="I just feel like it."), ev("vote", voter="Flo", target="Ann"),
        ev("thought", speaker="Cy", thought="Ann is deflecting a lot."), ev("vote", voter="Cy", target="Di"),   # names the wrong player
    )
    # Di and Ed name who they voted for. Flo names nobody, and Cy's reasoning is about Ann but the vote went to Di.
    assert c["vote_reasons"] == 4 and c["vote_reason_names_target"] == 2
    assert (c["vote_basis_behavior_only"], c["vote_basis_concrete"], c["vote_basis_none"]) == (2, 1, 1)


def test_statements_about_the_record_are_checked():
    c = counts(
        ev("vote", 1, voter="Di", target="Ed"),
        ev("death", 1, victim="Ed", role="villager", cause="vote"),
        ev("phase", 2, "night"), ev("kill_decision", 2, "night", target="Flo"), ev("no_death", 2),
        ev("speech", 2, speaker="Cy", message="Di voted for Ed yesterday, which I noticed."),          # true
        ev("speech", 2, speaker="Cy", message="Flo voted against Di yesterday."),                       # false: never happened
        ev("speech", 2, speaker="Flo", message="Ed was the detective, sadly."),                         # false: Ed was a villager
        ev("speech", 2, speaker="Flo", message="Ed was a villager, sadly."),                            # true
        ev("speech", 2, speaker="Di", message="Nobody died last night, so the doctor did something."), # true
        ev("speech", 2, speaker="Di", message="If nobody dies tonight we learn little."),               # hypothetical, skipped
        ev("speech", 2, speaker="Ed", message='Bob said "Di voted for Flo" which is nonsense.'),         # quoted, skipped
        ev("speech", 2, speaker="Flo", message="Bob claimed to be the detective earlier."),             # false: Bob never claimed
    )
    assert c["fact_total"] == 6 and c["fact_false"] == 3


def test_a_false_claim_about_a_night_death_is_caught():
    c = counts(ev("kill_decision", 1, "night", target="Ed"), ev("death", 1, victim="Ed", role="villager", cause="night"),
               ev("speech", 1, speaker="Flo", message="Nobody died last night, which is odd."))
    assert c["fact_total"] == 1 and c["fact_false"] == 1


def test_detective_claims_are_judged_by_how_the_town_responded():
    c = counts(
        ev("investigate", 1, "night", actor="Bob", target="Ann", result="MAFIA"),
        ev("speech", 1, speaker="Bob", message="I am the detective, and I investigated Ann. She is mafia."),
        ev("vote", 1, voter="Cy", target="Ann"), ev("vote", 1, voter="Di", target="Ann"), ev("vote", 1, voter="Ed", target="Bob"),
        ev("vote", 1, voter="Ann", target="Bob"), ev("vote", 1, voter="Bob", target="Ann"),
        ev("death", 1, victim="Ann", role="mafia", cause="vote"),
    )
    assert c["claim_true_total"] == 1 and c["claim_true_believed"] == 1          # Ann got 2 votes, Bob got 1 from the others
    # a mafia counterclaim is a false claim, and the town should not follow it
    c = counts(
        ev("investigate", 1, "night", actor="Bob", target="Ann", result="MAFIA"),
        ev("speech", 1, speaker="Ann", message="I am the detective, and I investigated Bob. He is mafia."),
        ev("vote", 1, voter="Cy", target="Bob"), ev("vote", 1, voter="Di", target="Bob"), ev("vote", 1, voter="Ed", target="Ann"),
        ev("death", 1, victim="Bob", role="detective", cause="vote"),
    )
    assert c["claim_false_total"] == 1 and c["claim_false_believed"] == 1       # the town believed the liar


def test_a_real_detective_naming_several_players_is_one_true_claim_not_several_false_ones():
    c = counts(
        ev("investigate", 1, "night", actor="Bob", target="Ann", result="MAFIA"),
        ev("speech", 1, speaker="Bob", message="I am the detective. Di and Ed are clear to me, but Ann is mafia, and Flo agrees."),
        ev("vote", 1, voter="Cy", target="Ann"), ev("vote", 1, voter="Di", target="Ann"), ev("vote", 1, voter="Ed", target="Ann"),
        ev("death", 1, victim="Ann", role="mafia", cause="vote"),
    )
    assert c["claim_true_total"] == 1 and c.get("claim_false_total", 0) == 0


def test_a_real_detective_who_found_nobody_makes_no_judgeable_claim():
    c = counts(ev("investigate", 1, "night", actor="Bob", target="Di", result="not mafia"),
               ev("speech", 1, speaker="Bob", message="I am the detective. Di is clear, so the mafia is among the rest of you."),
               ev("no_lynch", 1))
    assert c.get("claim_true_total", 0) == 0 and c.get("claim_false_total", 0) == 0


def test_a_false_claim_accuses_the_name_nearest_the_word_mafia():
    c = counts(
        ev("speech", 1, speaker="Di", message="Ed asked a fair question. I am the detective, I checked Flo, and Flo is mafia."),
        ev("vote", 1, voter="Cy", target="Flo"), ev("vote", 1, voter="Ed", target="Flo"), ev("vote", 1, voter="Ann", target="Di"),
        ev("death", 1, victim="Flo", role="villager", cause="vote"),
    )
    assert c["claim_false_total"] == 1 and c["claim_false_believed"] == 1       # accused is Flo, not Ed


def test_vote_reasoning_matches_names_in_any_case():
    c = counts(ev("thought", speaker="Ann", thought="ed is acting super defensive."), ev("vote", voter="Ann", target="Ed"))
    assert c["vote_reason_names_target"] == 1


def test_rates_sum_over_games_and_handle_empty_denominators():
    g = {"logic": logic_game(game(ev("thought", speaker="Di", thought="Ed is deflecting."), ev("vote", voter="Di", target="Ed")))}
    r = logic_rates([g, g])
    assert r["vote_reasons"] == 2 and r["reason_names_target_pct"] == 100.0 and r["basis_behavior_only_pct"] == 100.0
    assert r["fact_false_pct"] is None and r["doctor_vote_opportunities"] == 0


def test_log_without_setup_is_rejected():
    with pytest.raises(ValueError):
        logic_game([ev("start")])
