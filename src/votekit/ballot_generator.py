from abc import abstractmethod
from fractions import Fraction
from typing import Optional, Union
from votekit.profile import PreferenceProfile
from votekit.ballot import Ballot
from numpy.random import choice
import itertools as it
import random
import numpy as np
import pickle
from pathlib import Path
import math


class BallotGenerator:

    # cand is a set
    # number_of_ballots: int
    # candidates: list
    # ballot_length: Optional[int]
    # slate_to_candidate: Optional[dict]  # race: [candidate]
    # pref_interval_by_bloc: Optional[dict] = None  # race: {candidate : interval length}
    # demo_breakdown: Optional[dict] = None  # race: percentage

    def __init__(
        self,
        candidates: Union[list, dict],
        ballot_length: Optional[int] = None,
        hyperparams: Optional[dict] = {},
    ):
        """
        Base class for ballot generation models

        Args:
            candidates (list): list of candidates in the election
            ballot_length (Optional[int]): length of ballots to generate
        """

        self.ballot_length = (
            ballot_length if ballot_length is not None else len(candidates)
        )
        if isinstance(candidates, dict):
            self.slate_to_candidate = candidates
            self.candidates = list(
                {cand for cands in candidates.values() for cand in cands}
            )
        else:
            self.candidates = candidates
        self.ballot_length = (
            ballot_length if ballot_length is not None else len(self.candidates)
        )

        self.parameterized = False

        if hyperparams:
            if isinstance(candidates, dict):  # add type error
                self.set_params(candidates, **hyperparams)
                self.parameterized = True
            else:
                raise TypeError(
                    "'candidates' must be dictionary when hyperparameters are set"
                )

    @abstractmethod
    def generate_profile(self, number_of_ballots: int) -> PreferenceProfile:
        """
        Args:
            number_of_ballots (int): number of ballots to generate
        Returns:
            PreferenceProfile: a generated preference profiles
        """
        pass

    @staticmethod
    def round_num(num: float) -> int:
        """
        rounds up or down a float randomly

        Args:
            num (float): number to round

        Returns:
            int: a whole number
        """
        rand = np.random.random()
        return math.ceil(num) if rand > 0.5 else math.floor(num)

    @staticmethod
    def ballot_pool_to_profile(ballot_pool, candidates) -> PreferenceProfile:
        """
        Given a list of ballots and candidates, convert them into a Preference Profile

        Args:
            ballot_pool (list of tuple): a list of ballots, with tuple as their ranking
            candidates (list): a list of candidates

        Returns:
            PreferenceProfile: a preference profile representing the ballots in the election
        """
        ranking_counts: dict[tuple, int] = {}
        ballot_list: list[Ballot] = []

        for ranking in ballot_pool:
            tuple_rank = tuple(ranking)
            ranking_counts[tuple_rank] = (
                ranking_counts[tuple_rank] + 1 if tuple_rank in ranking_counts else 1
            )

        for ranking, count in ranking_counts.items():
            rank = [set([cand]) for cand in ranking]
            b = Ballot(ranking=rank, weight=Fraction(count))
            ballot_list.append(b)

        return PreferenceProfile(ballots=ballot_list, candidates=candidates)

    def set_params(
        self,
        candidates: dict,  # add type error for list here
        blocs: dict,
        cohesion: dict,
        alphas: dict,
        crossover: dict = {},
    ) -> None:
        """
        Generates perference intervals for slates based on pararmeters and specified models.
        """
        if sum(blocs.values()) != 1.0:
            raise ValueError(f"bloc proportions ({blocs.values()}) do not equal 1")

        def _preference_interval(
            alphas: dict, cohesion: int, bloc: str, candidates: dict
        ) -> dict:
            """
            Creates a preference interval for bloc of votes (e.g. W or POC)

            Inputs:
                alphas: dict of alpha parameters for Dirichlet distribution mapped to a
                    group (e.g. support for POC, or support for W)
                cohesion: support for candidates
                candidates dict: list of candidates mapped to their group

            Returns: perference interval, a dictionary with candidates mapped to
                their intervals
            """
            intervals = {}

            for group, alpha in alphas.items():
                num_cands = len(candidates[group])
                probs = list(np.random.dirichlet([alpha] * num_cands))
                for prob, cand in zip(probs, candidates[group]):
                    if group == bloc:  # e.g W for W cands
                        pi = cohesion
                    else:  # e.g W for POC cands
                        pi = 1 - cohesion
                    intervals[cand] = pi * prob

            return intervals

        interval_by_bloc = {}
        for bloc in blocs:
            interval = _preference_interval(
                alphas[bloc], cohesion[bloc], bloc, candidates
            )
            interval_by_bloc[bloc] = interval

        self.pref_interval_by_bloc = interval_by_bloc
        self.bloc_voter_prop = blocs
        self.bloc_crossover_rate = crossover


class ImpartialCulture(BallotGenerator):
    def generate_profile(self, number_of_ballots) -> PreferenceProfile:
        perm_set = it.permutations(self.candidates, self.ballot_length)
        # Create a list of every perm [['A', 'B', 'C'], ['A', 'C', 'B'], ...]
        perm_rankings = [list(value) for value in perm_set]

        ballot_pool = []

        for _ in range(number_of_ballots):
            index = random.randint(0, len(perm_rankings) - 1)
            ballot_pool.append(perm_rankings[index])

        return self.ballot_pool_to_profile(ballot_pool, self.candidates)


class ImpartialAnonymousCulture(BallotGenerator):
    def generate_profile(self, number_of_ballots) -> PreferenceProfile:
        perm_set = it.permutations(self.candidates, self.ballot_length)
        # Create a list of every perm [['A', 'B', 'C'], ['A', 'C', 'B'], ...]
        perm_rankings = [list(value) for value in perm_set]

        # IAC Process is equivalent to drawing from dirichlet dist with uniform parameters
        draw_probabilities = np.random.dirichlet([1] * len(perm_rankings))

        ballot_pool = []

        for _ in range(number_of_ballots):
            index = np.random.choice(
                range(len(perm_rankings)), 1, p=draw_probabilities
            )[0]
            ballot_pool.append(perm_rankings[index])

        return self.ballot_pool_to_profile(ballot_pool, self.candidates)


class PlackettLuce(BallotGenerator):
    def __init__(self, pref_interval_by_bloc=None, bloc_voter_prop=None, **data):
        """
        Plackett Luce Ballot Generation Model

        Args:
            pref_interval_by_bloc (dict): a mapping of slate to preference interval
            (ex. {race: {candidate : interval length}})
            bloc_voter_prop (dict): a mapping of slate to voter proportions
            (ex. {race: voter proportion})
        """
        if not pref_interval_by_bloc:
            self.pref_interval_by_bloc: dict = {}
            self.bloc_voter_prop: dict = {}

        # Call the parent class's __init__ method to handle common parameters
        super().__init__(**data)

        # Assign additional parameters specific to PlackettLuce
        if not self.parameterized:
            if round(sum(bloc_voter_prop.values())) != 1:
                raise ValueError("Voter proportion for blocs must sum to 1")
            for interval in pref_interval_by_bloc.values():
                if round(sum(interval.values())) != 1:
                    raise ValueError("Preference interval for candidates must sum to 1")
            if bloc_voter_prop.keys() != pref_interval_by_bloc.keys():
                raise ValueError("slates and blocs are not the same")

            self.pref_interval_by_bloc = pref_interval_by_bloc
            self.bloc_voter_prop = bloc_voter_prop

    def generate_profile(self, number_of_ballots) -> PreferenceProfile:
        ballot_pool = []

        for bloc in self.bloc_voter_prop.keys():
            # number of voters in this bloc
            num_ballots = self.round_num(number_of_ballots * self.bloc_voter_prop[bloc])
            pref_interval_dict = self.pref_interval_by_bloc[bloc]
            # creates the interval of probabilities for candidates supported by this block
            cand_support_vec = [pref_interval_dict[cand] for cand in self.candidates]

            for _ in range(num_ballots):
                # generates ranking based on probability distribution of candidate support
                ballot = list(
                    choice(
                        self.candidates,
                        self.ballot_length,
                        p=cand_support_vec,
                        replace=False,
                    )
                )

                ballot_pool.append(ballot)

        pp = self.ballot_pool_to_profile(
            ballot_pool=ballot_pool, candidates=self.candidates
        )
        return pp


class BradleyTerry(BallotGenerator):
    def __init__(self, pref_interval_by_bloc=None, bloc_voter_prop=None, **data):
        """
        Bradley Terry Ballot Generation Model

        Args:
            pref_interval_by_bloc (dict): a mapping of slate to preference interval
            (ex. {race: {candidate : interval length}})
            bloc_voter_prop (dict): a mapping of slate to voter proportions
            (ex. {race: voter proportion})
        """

        if not pref_interval_by_bloc:
            self.pref_interval_by_bloc: dict = {}
            self.bloc_voter_prop: dict = {}

        # Call the parent class's __init__ method to handle common parameters
        super().__init__(**data)

        if not self.parameterized:
            if round(sum(bloc_voter_prop.values())) != 1:
                raise ValueError("Voter proportion for blocs must sum to 1")
            for interval in pref_interval_by_bloc.values():
                if round(sum(interval.values())) != 1:
                    raise ValueError("Preference interval for candidates must sum to 1")
            if bloc_voter_prop.keys() != pref_interval_by_bloc.keys():
                raise ValueError("slates and blocs are not the same")

            # Assign additional parameters specific to Bradley Terrys
            self.pref_interval_by_bloc = pref_interval_by_bloc
            self.bloc_voter_prop = bloc_voter_prop

    # TODO: convert to dynamic programming method of calculation

    def _calc_prob(self, permutations: list[tuple], cand_support_dict: dict) -> dict:
        """
        given a list of rankings and the preference interval,
        calculates the probability of observing each ranking

        Args:
            permutations (list[tuple]): a list of permuted rankings
            cand_support_dict (dict): a mapping from candidate to their
            support (preference interval)

        Returns:
            dict: a mapping of the rankings to their probability
        """
        ranking_to_prob = {}
        for ranking in permutations:
            prob = 1
            for i in range(len(ranking)):
                cand_i = ranking[i]
                greater_cand_support = cand_support_dict[cand_i]
                for j in range(i + 1, len(ranking)):
                    cand_j = ranking[j]
                    cand_support = cand_support_dict[cand_j]
                    prob *= greater_cand_support / (greater_cand_support + cand_support)
            ranking_to_prob[ranking] = prob
        return ranking_to_prob

    def generate_profile(self, number_of_ballots) -> PreferenceProfile:

        permutations = list(it.permutations(self.candidates, self.ballot_length))
        ballot_pool: list[list] = []

        for bloc in self.bloc_voter_prop.keys():
            num_ballots = self.round_num(number_of_ballots * self.bloc_voter_prop[bloc])
            pref_interval_dict = self.pref_interval_by_bloc[bloc]

            ranking_to_prob = self._calc_prob(
                permutations=permutations, cand_support_dict=pref_interval_dict
            )

            indices = range(len(ranking_to_prob))
            prob_distrib = list(ranking_to_prob.values())
            prob_distrib = [float(p) / sum(prob_distrib) for p in prob_distrib]

            ballots_indices = choice(
                indices,
                num_ballots,
                p=prob_distrib,
                replace=True,
            )

            rankings = list(ranking_to_prob.keys())
            ballots = [rankings[i] for i in ballots_indices]

            ballot_pool = ballot_pool + ballots

        pp = self.ballot_pool_to_profile(
            ballot_pool=ballot_pool, candidates=self.candidates
        )
        return pp


class AlternatingCrossover(BallotGenerator):
    def __init__(
        self,
        slate_to_candidate=None,
        pref_interval_by_bloc=None,
        bloc_voter_prop=None,
        bloc_crossover_rate=None,
        **data,
    ):
        """
        Alternating Crossover Ballot Generation Model

        Args:
            slate_to_candidate (dict): a mapping of slate to candidates
            (ex. {race: [candidate]})
            pref_interval_by_bloc (dict): a mapping of bloc to preference interval
            (ex. {race: {candidate : interval length}})
            bloc_voter_prop (dict): a mapping of the percentage of total voters per bloc
            (ex. {race: 0.5})
            bloc_crossover_rate (dict): a mapping of percentage of crossover voters per bloc
            (ex. {race: {other_race: 0.5}})
        """
        if not pref_interval_by_bloc:
            self.slate_to_candidate: dict = {}
            self.pref_interval_by_bloc: dict = {}
            self.bloc_voter_prop: dict = {}
            self.bloc_crossover_rate: dict = {}

        # Call the parent class's __init__ method to handle common parameters
        super().__init__(**data)

        # Assign additional parameters specific to AC
        if not self.parameterized:
            if round(sum(bloc_voter_prop.values())) != 1:
                raise ValueError("Voter proportion for blocs must sum to 1")
            for interval in pref_interval_by_bloc.values():
                if round(sum(interval.values())) != 1:
                    raise ValueError("Preference interval for candidates must sum to 1")
            if (
                slate_to_candidate.keys()
                != bloc_voter_prop.keys()
                != pref_interval_by_bloc.keys()
            ):
                raise ValueError("slates and blocs are not the same")

            self.slate_to_candidate = slate_to_candidate
            self.pref_interval_by_bloc = pref_interval_by_bloc
            self.bloc_voter_prop = bloc_voter_prop
            self.bloc_crossover_rate = bloc_crossover_rate

    def generate_profile(self, number_of_ballots) -> PreferenceProfile:

        ballot_pool = []

        for bloc in self.bloc_voter_prop.keys():

            num_ballots = self.round_num(number_of_ballots * self.bloc_voter_prop[bloc])
            crossover_dict = self.bloc_crossover_rate[bloc]
            pref_interval_dict = self.pref_interval_by_bloc[bloc]

            # generates crossover ballots from each bloc (allowing for more than two blocs)
            for opposing_slate in crossover_dict.keys():
                crossover_rate = crossover_dict[opposing_slate]
                num_crossover_ballots = self.round_num(crossover_rate * num_ballots)

                opposing_cands = self.slate_to_candidate[opposing_slate]
                bloc_cands = self.slate_to_candidate[bloc]

                for _ in range(num_crossover_ballots):
                    pref_for_opposing = [
                        pref_interval_dict[cand] for cand in opposing_cands
                    ]
                    # convert to probability distribution
                    pref_for_opposing = [
                        p / sum(pref_for_opposing) for p in pref_for_opposing
                    ]

                    pref_for_bloc = [pref_interval_dict[cand] for cand in bloc_cands]
                    # convert to probability distribution
                    pref_for_bloc = [p / sum(pref_for_bloc) for p in pref_for_bloc]

                    bloc_cands = list(
                        choice(
                            bloc_cands,
                            p=pref_for_bloc,
                            size=len(bloc_cands),
                            replace=False,
                        )
                    )
                    opposing_cands = list(
                        choice(
                            opposing_cands,
                            size=len(opposing_cands),
                            p=pref_for_opposing,
                            replace=False,
                        )
                    )

                    # alternate the bloc and opposing bloc candidates to create crossover ballots
                    if bloc != opposing_slate:  # alternate
                        ballot = [
                            item
                            for pair in zip(opposing_cands, bloc_cands)
                            for item in pair
                            if item is not None
                        ]

                    # check that ballot_length is shorter than total number of cands
                    ballot_pool.append(ballot)

                # Bloc ballots
                for _ in range(num_ballots - num_crossover_ballots):
                    ballot = bloc_cands + opposing_cands
                    ballot_pool.append(ballot)

        pp = self.ballot_pool_to_profile(
            ballot_pool=ballot_pool, candidates=self.candidates
        )
        return pp


class OneDimSpatial(BallotGenerator):
    def generate_profile(self, number_of_ballots) -> PreferenceProfile:
        candidate_position_dict = {c: np.random.normal(0, 1) for c in self.candidates}
        voter_positions = np.random.normal(0, 1, number_of_ballots)

        ballot_pool = []

        for vp in voter_positions:
            distance_dict = {
                c: abs(v - vp) for c, v, in candidate_position_dict.items()
            }
            candidate_order = sorted(distance_dict, key=distance_dict.__getitem__)
            ballot_pool.append(candidate_order)

        return self.ballot_pool_to_profile(ballot_pool, self.candidates)


class CambridgeSampler(BallotGenerator):
    def __init__(
        self,
        slate_to_candidate=None,
        pref_interval_by_bloc=None,
        bloc_voter_prop=None,
        bloc_crossover_rate=None,
        path: Optional[Path] = None,
        **data,
    ):
        if not pref_interval_by_bloc:
            self.slate_to_candidate: dict = {}
            self.pref_interval_by_bloc: dict = {}
            self.bloc_voter_prop: dict = {}
            self.bloc_crossover_rate: dict = {}
        # Call the parent class's __init__ method to handle common parameters
        super().__init__(**data)

        # Assign additional parameters specific to
        if not self.parameterized:
            self.slate_to_candidate = slate_to_candidate
            self.pref_interval_by_bloc = pref_interval_by_bloc
            self.bloc_voter_prop = bloc_voter_prop
            self.bloc_crossover_rate = bloc_crossover_rate

        if path:
            self.path = path
        else:
            BASE_DIR = Path(__file__).resolve().parents[2]
            DATA_DIR = BASE_DIR / "tests/data/"
            self.path = Path(DATA_DIR, "Cambridge_09to17_ballot_types.p")

    def generate_profile(self, number_of_ballots: int) -> PreferenceProfile:

        with open(self.path, "rb") as pickle_file:
            ballot_frequencies = pickle.load(pickle_file)

        ballot_pool = []

        blocs = self.slate_to_candidate.keys()
        for bloc in blocs:
            # compute the number of voters in this bloc
            bloc_voters = self.round_num(self.bloc_voter_prop[bloc] * number_of_ballots)

            # store the opposition bloc
            opp_bloc = next(iter(set(blocs).difference(set(bloc))))

            # compute how many ballots list a bloc candidate first
            bloc_first_count = sum(
                [
                    freq
                    for ballot, freq in ballot_frequencies.items()
                    if ballot[0] == bloc
                ]
            )

            # Compute the pref interval for this bloc
            pref_interval_dict = self.pref_interval_by_bloc[bloc]

            # compute the relative probabilities of each ballot
            # sorted by ones where the ballot lists the bloc first
            # and those that list the opp first
            prob_ballot_given_bloc_first = {
                ballot: freq / bloc_first_count
                for ballot, freq in ballot_frequencies.items()
                if ballot[0] == bloc
            }
            prob_ballot_given_opp_first = {
                ballot: freq / bloc_first_count
                for ballot, freq in ballot_frequencies.items()
                if ballot[0] == opp_bloc
            }

            # Generate ballots
            for _ in range(bloc_voters):
                # Randomly choose first choice based off
                # bloc crossover rate
                first_choice = np.random.choice(
                    [bloc, opp_bloc],
                    p=[
                        1 - self.bloc_crossover_rate[bloc][opp_bloc],
                        self.bloc_crossover_rate[bloc][opp_bloc],
                    ],
                )
                # Based on first choice, randomly choose
                # ballots weighted by Cambridge frequency
                if first_choice == bloc:
                    bloc_ordering = random.choices(
                        list(prob_ballot_given_bloc_first.keys()),
                        weights=list(prob_ballot_given_bloc_first.values()),
                        k=1,
                    )[0]
                else:
                    bloc_ordering = random.choices(
                        list(prob_ballot_given_opp_first.keys()),
                        weights=list(prob_ballot_given_opp_first.values()),
                        k=1,
                    )[0]

                # Now turn bloc ordering into candidate ordering
                pl_ordering = list(
                    choice(
                        list(pref_interval_dict.keys()),
                        self.ballot_length,
                        p=list(pref_interval_dict.values()),
                        replace=False,
                    )
                )
                ordered_bloc_slate = [
                    c for c in pl_ordering if c in self.slate_to_candidate[bloc]
                ]
                ordered_opp_slate = [
                    c for c in pl_ordering if c in self.slate_to_candidate[opp_bloc]
                ]

                # Fill in the bloc slots as determined
                # With the candidate ordering generated with PL
                full_ballot = []
                for b in bloc_ordering:
                    if b == bloc:
                        if ordered_bloc_slate:
                            full_ballot.append(ordered_bloc_slate.pop(0))
                    else:
                        if ordered_opp_slate:
                            full_ballot.append(ordered_opp_slate.pop(0))

                ballot_pool.append(tuple(full_ballot))

        pp = self.ballot_pool_to_profile(
            ballot_pool=ballot_pool, candidates=self.candidates
        )
        return pp
