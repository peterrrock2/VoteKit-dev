from .abstract_ranking import RankingElection
from ....pref_profile import PreferenceProfile
from ...election_state import ElectionState
from ....utils import (
    elect_cands_from_set_ranking,
    remove_cand,
    validate_score_vector,
    score_profile_from_rankings,
)
from typing import Optional, Union, Sequence, Literal
from fractions import Fraction
from functools import partial


class Borda(RankingElection):
    r"""
    Borda election. Positional voting system that assigns a decreasing number of points to
    candidates based on their ordering. The conventional score vector is :math:`(n, n-1, \dots, 1)`
    where :math:`n` is the number of candidates. Candidates with the highest scores are elected.
    This class uses the `utils.score_profile_from_rankings()` to handle ballots with ties and
    missing candidates.

    Args:
        profile (PreferenceProfile): Profile to conduct election on.
        m (int, optional): Number of seats to elect. Defaults to 1.
        score_vector (Sequence[Union[float, Fraction]], optional): Score vector. Should be
            non-increasing and non-negative. Vector should be as long as the number of candidates.
            If it is shorter, we add 0s. Defaults to None, which is the conventional Borda vector.
        tiebreak (str, optional): Tiebreak method to use. Options are None, 'random', and
            'first_place'. Defaults to None, in which case a tie raises a ValueError.
        scoring_tie_convention (Literal["high", "average", "low"], optional): How to award points
            for tied rankings. Defaults to "low", where any candidates tied receive the lowest
            possible points for their position, eg three people tied for 3rd would each receive the
            points for 5th. "high" awards the highest possible points, so in the previous example,
            they would each receive the points for 3rd. "average" averages the points, so they would
            each receive the points for 4th place.

    """

    def __init__(
        self,
        profile: PreferenceProfile,
        m: int = 1,
        score_vector: Optional[Sequence[Union[float, Fraction]]] = None,
        tiebreak: Optional[str] = None,
        scoring_tie_convention: Literal["high", "average", "low"] = "low",
    ):
        self.m = m
        self.tiebreak = tiebreak
        if not score_vector:
            score_vector = list(range(profile.max_ballot_length, 0, -1))

        validate_score_vector(score_vector)
        self.score_vector = score_vector
        score_function = partial(
            score_profile_from_rankings,
            score_vector=score_vector,
            to_float=False,
            tie_convention=scoring_tie_convention,
        )
        super().__init__(profile, score_function=score_function, sort_high_low=True)

    def _is_finished(self):
        # single round election
        if len(self.election_states) == 2:
            return True
        return False

    def _run_step(
        self, profile: PreferenceProfile, prev_state: ElectionState, store_states=False
    ) -> PreferenceProfile:
        """
        Run one step of an election from the given profile and previous state.

        Args:
            profile (PreferenceProfile): Profile of ballots.
            prev_state (ElectionState): The previous ElectionState.
            store_states (bool, optional): True if `self.election_states` should be updated with the
                ElectionState generated by this round. This should only be True when used by
                `self._run_election()`. Defaults to False.

        Returns:
            PreferenceProfile: The profile of ballots after the round is completed.
        """
        # since borda is the score function, the remaining cands from round 0
        # are ranked by borda scores
        # raises a ValueError is tiebreak is None and a tie occurs.
        elected, remaining, tie_resolution = elect_cands_from_set_ranking(
            prev_state.remaining, self.m, profile=profile, tiebreak=self.tiebreak
        )

        new_profile = remove_cand([c for s in elected for c in s], profile)
        if store_states:
            if self.score_function:  # mypy
                scores = self.score_function(new_profile)
            else:
                raise ValueError()

            # if there was a tiebreak, store resolution
            if tie_resolution:
                tiebreaks = {tie_resolution[0]: tie_resolution[1]}
            else:
                tiebreaks = {}

            new_state = ElectionState(
                round_number=1,  # single shot election
                remaining=remaining,
                elected=elected,
                scores=scores,
                tiebreaks=tiebreaks,
            )

            self.election_states.append(new_state)

        return new_profile
