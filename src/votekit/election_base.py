from abc import ABC, abstractmethod
from itertools import permutations
import math

from .ballot import Ballot
from .pref_profile import PreferenceProfile
from .election_state import ElectionState


class Election(ABC):
    """
    Abstract base class for election types.

    Includes functions to resolve input ties included in PreferenceProfile
    """

    def __init__(self, profile: PreferenceProfile, ties: bool = False):
        if ties:
            self.__profile = profile
        else:
            self.__profile = self.resolve_input_ties(profile)

        self.state = ElectionState(curr_round=0, profile=self.__profile)

    @abstractmethod
    def run_step(self):
        pass

    @abstractmethod
    def run_election(self):
        pass

    def resolve_input_ties(self, profile: PreferenceProfile) -> PreferenceProfile:
        """
        Takes in a PeferenceProfile with potential ties in a ballot. Replaces
        ballots with ties with fractionally weighted ballots corresonding to
        all permutation of the tied ranking
        """
        new_ballots = []
        old_ballots = profile.get_ballots()

        for ballot in old_ballots:
            if not any(len(rank) > 1 for rank in ballot.ranking):
                new_ballots.append(ballot)
            else:
                num_ties = 0
                for rank in ballot.ranking:
                    if len(rank) > 1:
                        num_ties += 1

                resolved_ties = fix_ties(ballot)
                new_ballots += recursively_fix_ties(resolved_ties, num_ties)

        return PreferenceProfile(ballots=new_ballots)


# helpers
def recursively_fix_ties(ballot_lst: list[Ballot], num_ties: int) -> list[Ballot]:
    """
    Recursively fixes ties in a ballot in the case there is more then one tie
    """
    # base case, if only one tie to resolved return the list of already
    # resolved ballots
    if num_ties == 1:
        return ballot_lst

    # in the event multiple positions have ties
    else:
        update = set()
        for ballot in ballot_lst:
            update.update(set(fix_ties(ballot)))

        return recursively_fix_ties(list(update), num_ties - 1)


def fix_ties(ballot: Ballot) -> list[Ballot]:
    """
    Helper function for recursively_fix_ties. Resolves the first appearing
    tied rank in the input ballot by return list of permuted ballots
    """

    ballots = []
    for idx, rank in enumerate(ballot.ranking):
        if len(rank) > 1:
            for order in permutations(rank):
                resolved = []
                for cand in order:
                    resolved.append(set(cand))
                ballots.append(
                    Ballot(
                        id=ballot.id,
                        ranking=ballot.ranking[:idx]
                        + resolved
                        + ballot.ranking[idx + 1 :],
                        weight=ballot.weight / math.factorial(len(rank)),
                        voters=ballot.voters,
                    )
                )

    return ballots
