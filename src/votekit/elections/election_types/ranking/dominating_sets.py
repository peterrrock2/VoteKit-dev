from .abstract_ranking import RankingElection
from ....pref_profile import PreferenceProfile
from ...election_state import ElectionState
from ....utils import remove_cand
from ....graphs import PairwiseComparisonGraph


class DominatingSets(RankingElection):
    """
    A "dominating set" is any set S of candidates such that everyone in S beats everyone outside of
    S head-to-head. The top tier (which is well defined) is often called the "Smith set," and if it
    is just one person, they are called the "Condorcet candidate." The Smith method of election
    declares the Smith set to be the winners, which means that users do not get to specify the
    number of winners.

    Args:
        profile (PreferenceProfile): Profile to conduct election on.

    """

    def __init__(self, profile: PreferenceProfile):
        super().__init__(profile)

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
        Computes the dominating tiers and returns the highest tier, candidates that beat
        every other candidate in head-to-head comparisons.

        Args:
            profile (PreferenceProfile): Profile of ballots.
            prev_state (ElectionState): The previous ElectionState.
            store_states (bool, optional): True if `self.election_states` should be updated with the
                ElectionState generated by this round. This should only be True when used by
                `self._run_election()`. Defaults to False.

        Returns:
            PreferenceProfile: The profile of ballots after the round is completed.
        """

        pwc_graph = PairwiseComparisonGraph(profile)
        dominating_tiers = pwc_graph.get_dominating_tiers()
        new_profile = remove_cand(list(dominating_tiers[0]), profile)

        if store_states:
            elected = (frozenset(dominating_tiers[0]),)
            remaining = tuple([frozenset(s) for s in dominating_tiers[1:]])

            self.election_states.append(
                ElectionState(
                    round_number=prev_state.round_number + 1,
                    elected=elected,
                    remaining=remaining,
                )
            )

        return new_profile
