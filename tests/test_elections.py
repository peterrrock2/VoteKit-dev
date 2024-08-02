from fractions import Fraction
from pathlib import Path
import pytest
import random
import numpy as np

from votekit.ballot import Ballot
from votekit.cvr_loaders import load_scottish, load_csv  # type:ignore
from votekit.elections.election_types import (
    STV,
    SequentialRCV,
    RandomDictator,
    BoostedRandomDictator,
)
from votekit.elections.transfers import fractional_transfer, random_transfer
from votekit.pref_profile import PreferenceProfile
from votekit.utils import (
    remove_cand,
    compute_votes,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data/csv/"


test_profile = load_csv(DATA_DIR / "test_election_A.csv")
mn_profile = load_csv("src/votekit/data/mn_2013_cast_vote_record.csv")


def test_droop_default_parameter():
    pp, seats, cand_list, cand_to_party, ward = load_scottish(
        DATA_DIR / "scot_wardy_mc_ward.csv"
    )

    election = STV(pp, fractional_transfer, seats=seats)

    droop_quota = int((126 + 9 + 10 + 1) / (1 + 1)) + 1

    assert election.threshold == droop_quota


def test_droop_inputed_parameter():
    pp, seats, cand_list, cand_to_party, ward = load_scottish(
        DATA_DIR / "scot_wardy_mc_ward.csv"
    )

    election = STV(pp, fractional_transfer, seats=seats, quota="Droop")

    droop_quota = int((126 + 9 + 10 + 1) / (1 + 1)) + 1

    assert election.threshold == droop_quota


def test_quota_misspelled_parameter():
    pp, seats, cand_list, cand_to_party, ward = load_scottish(
        DATA_DIR / "scot_wardy_mc_ward.csv"
    )

    with pytest.raises(ValueError):
        _ = STV(pp, fractional_transfer, seats=seats, quota="droops")


def test_hare_quota():
    pp, seats, cand_list, cand_to_party, ward = load_scottish(
        DATA_DIR / "scot_wardy_mc_ward.csv"
    )

    election = STV(pp, fractional_transfer, seats=seats, quota="hare")

    hare_quota = int((126 + 9 + 10 + 1) / 1)

    assert election.threshold == hare_quota


def test_max_votes_toy():
    max_cand = "a"
    cands = test_profile.get_candidates()
    ballots = test_profile.get_ballots()
    _, results = compute_votes(cands, ballots)
    max_votes = [
        candidate
        for candidate, votes in results.items()
        if votes == max(results.values())
    ]
    assert results[max_cand] == 6
    assert max_votes[0] == max_cand


def test_min_votes_mn():
    min_cand = "JOHN CHARLES WILSON"
    cands = mn_profile.get_candidates()
    ballots = mn_profile.get_ballots()
    _, results = compute_votes(cands, ballots)
    max_votes = [
        candidate
        for candidate, votes in results.items()
        if votes == min(results.values())
    ]
    assert max_votes[0] == min_cand


def test_remove_cand_not_inplace():
    remove = "a"
    ballots = test_profile.get_ballots()
    new_ballots = remove_cand(remove, ballots)
    assert ballots != new_ballots


def test_remove_fake_cand():
    remove = "z"
    ballots = test_profile.get_ballots()
    new_ballots = remove_cand(remove, ballots)
    assert ballots == new_ballots


def test_remove_and_shift():
    remove = "a"
    ballots = test_profile.get_ballots()
    new_ballots = remove_cand(remove, ballots)
    for ballot in new_ballots:
        if len(ballot.ranking) == len(ballots[0].ranking):
            assert len(ballot.ranking) == len(ballots[0].ranking)


def test_irv_winner_mn():
    irv = STV(mn_profile, fractional_transfer, 1, ballot_ties=False)
    outcome = irv.run_election()
    winner = "BETSY HODGES"
    assert [{winner}] == outcome.elected


def test_stv_winner_mn():
    irv = STV(mn_profile, fractional_transfer, 3, ballot_ties=False)
    outcome = irv.run_election()
    winners = [{"BETSY HODGES"}, {"MARK ANDREW"}, {"DON SAMUELS"}]
    assert winners == outcome.winners()


def test_runstep_seats_full_at_start():
    mock = STV(test_profile, fractional_transfer, 9, ballot_ties=False)
    step = mock._profile
    assert step == test_profile


def test_rand_transfer_func_mock_data():
    winner = "A"
    ballots = [
        Ballot(ranking=({"A"}, {"C"}, {"B"}), weight=Fraction(2)),
        Ballot(ranking=({"A"}, {"B"}, {"C"}), weight=Fraction(1)),
    ]
    votes = {"A": 3}
    threshold = 1

    ballots_after_transfer = random_transfer(
        winner=winner, ballots=ballots, votes=votes, threshold=threshold
    )

    counts, _ = compute_votes(candidates=["B", "C"], ballots=ballots_after_transfer)

    assert counts[0].votes == Fraction(1) or counts[0].votes == Fraction(2)


def test_rand_transfer_assert():
    winner = "A"
    ballots = [
        Ballot(ranking=({"A"}, {"C"}, {"B"}), weight=Fraction(1000)),
        Ballot(ranking=({"A"}, {"B"}, {"C"}), weight=Fraction(1000)),
    ]
    votes = {"A": 2000}
    threshold = 1000

    ballots_after_transfer = random_transfer(
        winner=winner, ballots=ballots, votes=votes, threshold=threshold
    )
    counts, _ = compute_votes(candidates=["B", "C"], ballots=ballots_after_transfer)

    assert 400 < counts[0].votes < 600


def test_toy_rcv():
    """
    example toy election taken from David McCune's code with known winners c and d
    """
    known_winners = [{"c"}, {"d"}]
    ballot_list = [
        Ballot(ranking=[{"a"}, {"b"}], weight=Fraction(1799)),
        Ballot(ranking=[{"a"}, {"b"}, {"c"}, {"d"}], weight=Fraction(1801)),
        Ballot(ranking=[{"a"}, {"c"}, {"d"}], weight=Fraction(100)),
        Ballot(ranking=[{"b"}, {"c"}, {"a"}, {"d"}], weight=Fraction(901)),
        Ballot(ranking=[{"b"}, {"d"}], weight=Fraction(900)),
        Ballot(ranking=[{"c"}, {"b"}, {"d"}, {"a"}], weight=Fraction(498)),
        Ballot(ranking=[{"c"}, {"d"}, {"a"}], weight=Fraction(2000)),
        Ballot(ranking=[{"d"}, {"b"}], weight=Fraction(1400)),
        Ballot(ranking=[{"d"}, {"c"}], weight=Fraction(601)),
    ]
    toy_pp = PreferenceProfile(ballots=ballot_list)
    seq_RCV = SequentialRCV(profile=toy_pp, seats=2, ballot_ties=False)
    toy_winners = seq_RCV.run_election().winners()
    assert known_winners == toy_winners


def test_random_dictator():
    # set seed for more predictable results
    random.seed(919717)

    # simple 3 candidate election
    candidates = ["A", "B", "C"]
    ballots = [
        Ballot(ranking=[{"A"}, {"B"}, {"C"}], weight=3),
        Ballot(ranking=[{"B"}, {"A"}, {"C"}]),
        Ballot(ranking=[{"C"}, {"B"}, {"A"}]),
    ]
    test_profile = PreferenceProfile(ballots=ballots, candidates=candidates)

    # count the number of wins over a set of trials
    winner_counts = {c: 0 for c in candidates}
    trials = 10000
    for t in range(trials):
        election = RandomDictator(test_profile, 1)
        election.run_election()
        winner = list(election.state.winners()[0])[0]
        winner_counts[winner] += 1

    # check to make sure that the fraction of wins matches the true probability
    assert np.allclose(3 / 5, winner_counts["A"] / trials, atol=1e-2)


def test_boosted_random_dictator():
    # set seed for more predictable results
    random.seed(919717)

    # simple 3 candidate election
    candidates = ["A", "B", "C"]
    ballots = [
        Ballot(ranking=[{"A"}, {"B"}, {"C"}], weight=3),
        Ballot(ranking=[{"B"}, {"A"}, {"C"}]),
        Ballot(ranking=[{"C"}, {"B"}, {"A"}]),
    ]
    test_profile = PreferenceProfile(ballots=ballots, candidates=candidates)

    # count the number of wins over a set of trials
    winner_counts = {c: 0 for c in candidates}
    trials = 10000
    for t in range(trials):
        election = BoostedRandomDictator(test_profile, 1)
        election.run_election()
        winner = list(election.state.winners()[0])[0]
        winner_counts[winner] += 1

    # check to make sure that the fraction of wins matches the true probability
    assert np.allclose(
        1 / 2 * 3 / 5 + 1 / 2 * 9 / 11, winner_counts["A"] / trials, atol=1e-2
    )
