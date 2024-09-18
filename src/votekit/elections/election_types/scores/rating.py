from ....models import Election
from ....pref_profile import PreferenceProfile
from ...election_state import ElectionState
from ....utils import (
    score_profile_from_ballot_scores,
    elect_cands_from_set_ranking,
    remove_cand,
)
from typing import Optional, Union
from fractions import Fraction


class GeneralRating(Election):
    """
    General rating election. To fill :math:`m` seats, voters score each candidate from
    :math:`0-L`, where :math:`L` is some user-specified limit.  There is also a total budget of
    :math:`k` points per voter. The :math:`m` winners are those with the highest total score.

    Args:
        profile (PreferenceProfile): Profile to conduct election on.
        m (int, optional): Number of seats to elect. Defaults to 1.
        L (Union[float, Fraction], optional): Rating per candidate limit. Defaults to 1.
        k (Union[float, Fraction], optional): Budget per ballot limit. Defaults to None, in which
            case voters can score each candidate independently.
        tiebreak (str, optional): Tiebreak method to use. Options are None and 'random'.
            Defaults to None, in which case a tie raises a ValueError.

    """

    def __init__(
        self,
        profile: PreferenceProfile,
        m: int = 1,
        L: Union[float, Fraction] = 1,
        k: Optional[Union[float, Fraction]] = None,
        tiebreak: Optional[str] = None,
    ):
        if m <= 0:
            raise ValueError("m must be positive.")
        self.m = m
        if L <= 0:
            raise ValueError("L must be positive.")
        self.L = L
        if k and k <= 0:
            raise ValueError("k must be positive.")
        if k and L > k:
            raise ValueError("L must be less than or equal to k.")
        self.k = k
        self.tiebreak = tiebreak
        self._validate_profile(profile)
        super().__init__(
            profile, score_function=score_profile_from_ballot_scores, sort_high_low=True
        )

    def _validate_profile(self, profile: PreferenceProfile):
        """
        Ensures that every ballot has a score dictionary and each voter has not gone over their
        score limit per candidate and total budgrt. Raises a TypeError if no score dictionary,
        and a value error for budget/score limit violation.

        Args:
            profile (PreferenceProfile): Profile to validate.
        """

        for b in profile.ballots:
            if not b.scores:
                raise TypeError("All ballots must have score dictionary.")
            elif any(score > self.L for score in b.scores.values()):
                raise TypeError(
                    f"Ballot {b} violates score limit {self.L} per candidate."
                )
            elif any(score < 0 for score in b.scores.values()):
                raise TypeError(f"Ballot {b} must have non-negative scores.")

            if self.k:
                if sum(b.scores.values()) > self.k:
                    raise TypeError(f"Ballot {b} violates total score budget {self.k}.")

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
        # since score_profile_from_ballot_scores is the score function, the remaining cands from
        # round 0 are ranked by score
        # raises a ValueError is tiebreak is None and a tie occurs.
        elected, remaining, tie_resolution = elect_cands_from_set_ranking(
            prev_state.remaining, self.m, profile=profile, tiebreak=self.tiebreak
        )

        new_profile = remove_cand([c for s in elected for c in s], profile)

        if store_states:
            if self.score_function:
                scores = self.score_function(new_profile)
            else:
                raise ValueError()

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


class Rating(GeneralRating):
    """
    Rating election. To fill :math:`m` seats, voters score each candidate independently from
    :math:`0-L`, where :math:`L` is some user-specified limit.  The :math:`m` winners are those with
    the highest total score.

    Args:
        profile (PreferenceProfile): Profile to conduct election on.
        m (int, optional): Number of seats to elect. Defaults to 1.
        L (Union[float, Fraction], optional): Rating per candidate limit. Defaults to 1.
        tiebreak (str, optional): Tiebreak method to use. Options are None and 'random'.
            Defaults to None, in which case a tie raises a ValueError.

    """

    def __init__(
        self,
        profile: PreferenceProfile,
        m: int = 1,
        L: Union[float, Fraction] = 1,
        tiebreak: Optional[str] = None,
    ):
        super().__init__(profile, m=m, L=L, tiebreak=tiebreak)


class Limited(GeneralRating):
    r"""
    Voters can score each candidate, but have a total budget of :math:`k\le m` points.
    Winners are those with highest total score.

    Args:
        profile (PreferenceProfile): Profile to conduct election on.
        m (int, optional): Number of seats to elect. Defaults to 1.
        k (Union[float, Fraction], optional): Total budget per voter. Defaults to 1.
        tiebreak (str, optional): Tiebreak method to use. Options are None, and 'random'.
            Defaults to None, in which case a tie raises a ValueError.
    """

    def __init__(
        self,
        profile: PreferenceProfile,
        m: int = 1,
        k: Union[float, Fraction] = 1,
        tiebreak: Optional[str] = None,
    ):
        if k > m:
            raise ValueError("k must be less than or equal to m.")

        super().__init__(profile, m=m, L=k, k=k, tiebreak=tiebreak)


class Cumulative(Limited):
    """
    Voters can score each candidate, but have a total budget of :math:`m` points, where :math:`m` is
    the number of seats to be filled. Winners are those with highest total score.

    Args:
        profile (PreferenceProfile): Profile to conduct election on.
        m (int, optional): Number of seats to elect. Defaults to 1.
        tiebreak (str, optional): Tiebreak method to use. Options are None, and 'random'.
            Defaults to None, in which case a tie raises a ValueError.
    """

    def __init__(
        self, profile: PreferenceProfile, m: int = 1, tiebreak: Optional[str] = None
    ):
        super().__init__(profile, m=m, k=m, tiebreak=tiebreak)