import numpy as np

import time

import matplotlib

import matplotlib.pyplot as plt

import matplotlib.colors as colors

import scipy.optimize as opt

from diploid import mating_models

from diploid import dispersal_models

from diploid import fitness_models

from diploid.constants import Const

from diploid.parameters import Params

from diploid import plot_util

plt.rcParams['figure.dpi'] = 100
# matplotlib.use('Qt5Agg')


class Trial:

    def __init__(self, params, plot_int=None):
        self.params = params
        self.time0 = time.time()
        self.time_vec = np.zeros(params.g + 1)
        self.complete = False
        self.t = params.g
        self.i0 = 0
        self.i1 = 0
        self.report_int = max(min(100, self.params.g // 10), 1)
        self.plot_int = plot_int
        self.figs = []
        self.type = params.history_type
        if self.type == "Pedigree":
            self.pedigree = Pedigree.new(params)
            self.get_pedigree()
        elif self.type == "AbbrevPedigree":
            self.abbrev_pedigree = AbbrevPedigree.new(params)
            self.get_abbrev_pedigree()
        elif self.type == "SubpopArr":
            self.subpop_arr = SubpopArr.initialize(params)
            self.get_subpop_arr()
        else:
            raise Exception(f"{self.type} is not a valid history type!")

    def get_pedigree(self):
        print("simulation initiated @ " + self.get_time_string())
        self.time_vec[self.params.g] = 0
        generation = Generation.get_founding(self.params)
        i1 = generation.sort_by_x_and_id(self.i0)
        self.update_i(i1)
        if self.plot_int:
            self.figs.append(generation.plot_subpops())
        while self.t > 0:
            self.pedigree.enter_gen(generation, self.i0, self.i1, flag=0)
            generation = self.cycle(generation)
        self.pedigree.enter_gen(generation, self.i0, self.i1, flag=1)
        self.pedigree.trim(self.i1)
        if self.plot_int:
            for fig in self.figs:
                fig.show()
        print("simulation complete")

    def get_abbrev_pedigree(self):
        print("simulation initiated @ " + self.get_time_string())
        generation = Generation.get_founding(self.params)
        i1 = generation.sort_by_x_and_id(self.i0)
        self.update_i(i1)
        self.abbrev_pedigree.save_first_gen(generation)
        self.time_vec[self.params.g] = 0
        if self.plot_int:
            self.figs.append(generation.plot_subpops())
        while self.t > 0:
            self.abbrev_pedigree.enter_gen(generation, self.i0, self.i1)
            generation = self.cycle(generation)
        self.abbrev_pedigree.enter_gen(generation, self.i0, self.i1)
        self.abbrev_pedigree.save_last_gen(generation)
        self.abbrev_pedigree.trim(self.i1)
        if self.plot_int:
            for fig in self.figs:
                fig.show()
        print("simulation complete")

    def get_subpop_arr(self):
        print("simulation initiated @ " + self.get_time_string())
        generation = Generation.get_founding(self.params)
        generation.sort_by_x_and_id(self.i0)
        self.time_vec[self.params.g] = 0
        if self.plot_int:
            self.figs.append(generation.plot_subpops())
        while self.t > 0:
            self.subpop_arr.enter_generation(generation)
            generation = self.cycle(generation)
            if self.t == 0:
                self.complete = True
        self.subpop_arr.enter_generation(generation)
        if self.plot_int:
            for fig in self.figs:
                fig.show()
        print("simulation complete")

    def cycle(self, generation):
        """Advance the simulation through a single cycle"""
        self.update_t()
        old_generation = generation
        old_generation.remove_dead()
        generation = old_generation.mate(old_generation, self.params)
        generation.disperse(self.params)
        generation.fitness(self.params)
        i1 = generation.sort_by_x_and_id(self.i1)
        self.update_i(i1)
        self.report()
        if self.plot_int:
            if self.t % self.plot_int == 0:
                self.figs.append(generation.plot_subpops())
        return generation

    def update_i(self, i1):
        """Update the upper and lower indices to appropriate new values"""
        self.i0 = self.i1
        self.i1 = i1

    def update_t(self):
        self.t -= 1
        if self.t == 0:
            self.complete = True

    def report(self):
        self.time_vec[self.t] = time.time() - self.time0
        if self.t % self.report_int == 0:
            t = self.time_vec[self.t]
            t_last = self.time_vec[self.t + self.report_int]
            mean_t = str(np.round((t - t_last) / self.report_int, 3))
            run_t = str(np.round(self.time_vec[self.t], 2))
            time_string = self.get_time_string()
            print(f"g{self.t : > 6} complete, runtime = {run_t : >8}"
                  + f" s, averaging {mean_t : >8} s/gen, @ {time_string :>8}")

    @staticmethod
    def get_time_string():
        return str(time.strftime("%H:%M:%S", time.localtime()))


class PedigreeLike:
    """The superclass of pedigree-like objects; operations on its child classes
    are the primary activity of this simulation. All pedigree child classes
    are built around long 2-dimensional numpy arrays and a Params class
    instance which defines the simulation parameters under which the pedigree
    exists

    Pedigree arrays must include a column of ids and two columns of parent ids.
    A time column is not strictly necessary but is included in all classes
    because it simplifies pedigree sampling and interpretation. x-coordinate,
    sex, alleles and state flag are further details which are utilized in
    generation arrays during simulation but do not necessarily need to be
    retained in pedigrees.
    """
    organism_axis = 0
    character_axis = 1
    n_subpops = 9
    n_loci = 2
    ploidy = 2
    n_alleles = 4
    adjust_fac = 1.01

    def __init__(self, arr, params):
        self.arr = arr
        self.params = params

    def get_n_organisms(self):
        """Return the total number of organisms recorded in the pedigree"""
        return np.shape(self.arr)[0]


class FullPedigree(PedigreeLike):
    """The superclass of pedigree-like objects, which includes Generation,
    Pedigree and SamplePedigree. These objects are each structured around a
    single large array of floats and a set of parameters.

    Attributes preceded by a single underscore give column indices which
    access the type of information implied by the attribute name.
    """
    dtype = np.float32
    n_cols = 11
    _sex = 0
    _id = 1
    _x = 2
    _t = 3
    _mat_id = 4
    _pat_id = 5
    _A_loc0 = 6
    _A_loc1 = 7
    _B_loc0 = 8
    _B_loc1 = 9
    _flag = 10
    _coordinates = [2, 3]
    _parents = [4, 5]
    _alleles = [6, 7, 8, 9]
    _A_loci = [6, 7]
    _B_loci = [8, 9]
    _mat_alleles = [6, 8]
    _pat_alleles = [7, 9]

    def __init__(self, arr, params):
        super().__init__(arr, params)

    def __len__(self):
        """Return the length of self.arr, which equals the number of organisms
        encoded in that array
        """
        return len(self.arr)

    def __getitem__(self, i):
        """Return the organism at index or indices i"""
        return self.arr[i, :]

    def get_sex(self):
        return self.arr[:, self._sex]

    def sex_split(self):
        """Get arrays containing only the female and male individuals of an
        array
        """
        females = self.arr[self.get_female_idx()]
        males = self.arr[self.get_male_idx()]
        return females, males

    def get_female_idx(self):
        """Return the indices of the females in the array"""
        return np.where(self.arr[:, self._sex] == 0)[0]

    def get_male_idx(self):
        """return the indices of the males in the array"""
        return np.where(self.arr[:, self._sex] == 1)[0]

    def get_males(self):
        """Return the subset of self.arr which is male"""
        return self.arr[self.get_male_idx()]

    def get_females(self):
        """Return the subset of self.arr which is female"""
        return self.arr[self.get_female_idx()]

    def get_n_females(self):
        """Return the number of females in a generation"""
        return np.size(self.get_female_idx())

    def get_n_males(self):
        """Return the number of males in a generation"""
        return np.size(self.get_male_idx())

    def get_sex_idx(self, sex):
        """Given an integer sex = 0 or sex = 1, return the appropriate sex"""
        return np.where(self.arr[:, self._sex] == sex)

    def get_ids(self):
        """Return a vector of all ids in the array"""
        return self.arr[:, self._id]

    def get_ids_at_idx(self, idx):
        """Return a vector of all ids at idx in the array"""
        return self.arr[idx, self._id]

    def sort_by_id(self):
        """Sort the generation by x coordinate. Sorting is vital to the
        correct operation of many Generation functions
        """
        ids = self.get_ids()
        self.arr = self.arr[ids.argsort()]

    def get_x(self):
        return self.arr[:, self._x]

    def get_female_x(self):
        """Return the vector of male x positions"""
        return self.arr[self.get_female_idx(), self._x]

    def get_male_x(self):
        """Return the vector of male x positions"""
        return self.arr[self.get_male_idx(), self._x]

    def get_t(self):
        return self.arr[:, self._t]

    def get_parents(self):
        return self.arr[:, self._parents].astype(np.int32)

    def get_alleles(self):
        return self.arr[:, self._alleles]

    def get_allele_sums(self):
        allele_sums = np.zeros((self.get_n_organisms(), 2))
        allele_sums[:, 0] = np.sum(self.arr[:, self._A_loci], axis=1)
        allele_sums[:, 1] = np.sum(self.arr[:, self._B_loci], axis=1)
        return allele_sums

    def get_subpop_idx(self):
        """Return a subpop index for each organism in the generation"""
        allele_sums = self.get_allele_sums()
        subpop_idx = np.zeros(self.get_n_organisms(), dtype=np.int32)
        for i in np.arange(9):
            idx = np.where((allele_sums[:, 0] == Const.allele_sums[i, 0])
                           & (allele_sums[:, 1] == Const.allele_sums[i, 1]))[0]
            subpop_idx[idx] = i
        return subpop_idx

    def get_signal_sums(self):
        """Return the sum of signal alleles for all individuals"""
        return np.sum(self.arr[:, self._A_loci], axis=1)

    def get_signal_indices(self):
        """Return the indices at which signal genotypes A1A1, A1A2, A2A2 occur
        """
        signal_sums = self.get_signal_sums()
        idx11 = np.where(signal_sums == 2)[0]
        idx12 = np.where(signal_sums == 3)[0]
        idx22 = np.where(signal_sums == 4)[0]
        return idx11, idx12, idx22

    def get_flags(self):
        """Return the flags column from self.arr"""
        return self.arr[:, self._flag]

    def get_flags_at_idx(self, idx):
        """Return the flag/s at a given index idx"""
        return self.arr[idx, self._flag]

    def set_flags(self, idx, x):
        """Flag individuals at index idx with flag x"""
        self.arr[idx, self._flag] = x

    def get_living(self):
        """Return the index of living organisms with flag = 1"""
        return np.where(self.arr[:, self._flag] == 1)[0]

    def get_flag_idx(self, flag):
        """Get the indices of all individuals with flag = flag"""
        return np.where(self.arr[:, self._flag] == flag)

    def set_all_flags(self, flag):
        """Set all flags which equal 1 to arg 'flag'"""
        flagged_1 = self.get_flag_idx(1)
        self.arr[flagged_1, self._flag] = flag

    def get_dead_idx(self):
        """Get the index of individuals with flag < 0"""
        return np.where(self.arr[:, self._flag] < 0)[0]


class Organism(FullPedigree):
    """A demonstration"""

    def __init__(self, sex, id, x, t, parent_ids, alleles, params):
        arr = np.zeros(self.n_cols)
        super().__init__(arr, params)
        self.arr[self._sex] = sex
        self.arr[self._id] = id
        self.arr[self._x] = x
        self.arr[self._t] = t
        self.arr[self._parents] = parent_ids
        self.arr[self._alleles] = alleles


class Generation(FullPedigree):
    """The fundamental unit of simulation. Composed of N rows, each
    representing an organism.
    """

    def __init__(self, n, x, t, parent_ids, alleles, params):
        """n corresponds to n_filled in the Pedigree"""
        arr = np.zeros((n, self.n_cols), dtype=self.dtype)
        super().__init__(arr, params)
        self.t = t
        arr[:, self._sex] = np.random.randint(0, 2, n)
        arr[:, self._x] = x
        arr[:, self._t] = t
        arr[:, self._mat_id] = parent_ids[:, 0]
        arr[:, self._pat_id] = parent_ids[:, 1]
        arr[:, self._alleles] = alleles
        arr[:, self._flag] = 1
        self.sort_by_x()

    @classmethod
    def get_founding(cls, params):
        """create the founding generation"""
        n = params.N
        t = params.g
        parent_ids = np.full((n, 2), -1, dtype=cls.dtype)
        alleles_ = []
        x_ = []
        for i, genotype in enumerate(Const.genotypes):
            n_ = params.subpop_n[i]
            if n_ > 0:
                alleles_.append(np.repeat(genotype[np.newaxis, :], n_, axis=0))
                lower, upper = params.subpop_lims[i]
                x_.append(np.random.uniform(lower, upper, n_))
        alleles = np.vstack(alleles_)
        x = np.concatenate(x_)
        return cls(n, x, t, parent_ids, alleles, params)

    @classmethod
    def mate(cls, old_generation, params):
        t = old_generation.t - 1
        mating_pairs = MatingPairs(old_generation, params)
        n = mating_pairs.get_n_organisms()
        x = mating_pairs.get_maternal_x()
        parent_ids = mating_pairs.get_parent_ids()
        alleles = mating_pairs.get_zygotes()
        return cls(n, x, t, parent_ids, alleles, params)

    @classmethod
    def merge(cls, gen1, gen2):
        """merge two generations with the same t value. useful for combining
        migrants into the primary generation
        """
        params = gen1.params
        t1 = gen1.t
        t2 = gen2.t
        n = gen1.get_n_organisms() + gen2.get_n_organisms()
        t = t1
        x = np.concatenate((gen1.get_x(), gen2.get_x()))
        parent_ids = np.vstack((gen1.get_parents(), gen2.get_parents()))
        alleles = np.vstack((gen1.get_alleles(), gen2.get_alleles()))
        return cls(n, x, t, parent_ids, alleles, params)

    def __add__(self, generation):
        # index handling is tricky
        if self.params != generation.params:
            print("Warning! Generations with different parameter sets have \
                  been added")
        params = self.params
        if self.t != generation.t:
            print("Warning! Generations with different times have been added")
        t = self.t
        n = len(self) + len(generation)
        x = np.concatenate((self.get_x(), generation.get_x()))
        parent_ids = np.vstack((self.get_parents(), generation.get_parents()))
        alleles = np.vstack((self.get_alleles(), generation.get_alleles()))
        return Generation(n, x, t, parent_ids, alleles, params)

    @classmethod
    def get_migrants(cls, x, species, t, params):
        N = len(x)
        parent_ids = np.full((N, 2), -1)
        alleles = np.full((N, cls.n_alleles), species)
        return cls(N, x, t, parent_ids, alleles, params)

    def __str__(self):
        n = self.get_n_organisms()
        return f"Generation object at t = {self.t} with N = {n}"

    def __repr__(self):
        """Does not conform to how a repr should behave :-("""
        n = self.get_n_organisms()
        return f"Generation object at t = {self.t} with N = {n}"

    def compute_n_offspring(self, params):
        """Get a vector of numbers of offspring"""
        local_K = params.K * 2 * params.density_bound
        density = self.compute_local_densities(params)
        expectation = 2 * np.exp(params.r * (1 - (density / local_K)))
        n_offspring_vec = np.random.poisson(expectation)
        return n_offspring_vec

    def compute_local_densities(self, params):
        """Compute the population densities about each female in the
        generation
        """
        b = params.density_bound
        females = self.get_females()
        bound = self.compute_bounds(females, self.arr, [-b, b])
        densities = bound[:, 1]
        densities -= bound[:, 0]
        densities = densities + self.edge_density_adjustment(params)
        return densities

    def edge_density_adjustment(self, params):
        """Compute a vector of density adjustments for the edges of space"""
        b = params.density_bound
        k = params.K * b
        females = self.get_females()
        f_x = females[:, self._x]
        adjustment = np.zeros(len(f_x), dtype=np.float32)
        adjustment[f_x < b] = (b - f_x[f_x < b]) / b * k
        adjustment[f_x > 1 - b] = (f_x[f_x > 1 - b] - 1 + b) / b * k
        return adjustment

    def compute_pref_idx(self):
        """Compute indices to select the correct preference vector index for each
        female's preference: B1B1 0, B1B2 1, B2B2 2
        """
        female_idx = self.get_female_idx()
        B_sums = np.sum(self.arr[np.ix_(female_idx, self._B_loci)], axis = 1)
        pref_idx = (B_sums - 2).astype(np.int32)
        return pref_idx

    def compute_pref_matrix(self, params):
        """Compute 3 vectors of preferences targeting 'trait' in 'sex'.
        Preference vecs are combined in a 2d array in the order B1B1, B1B2,
        B2B2
        """
        male_idx = self.get_male_idx()
        A_sums = np.sum(self.arr[np.ix_(male_idx, self._A_loci)], axis = 1)
        trait_vec = (A_sums - 2).astype(np.int32)
        pref_matrix = np.full((self.get_n_males(), 3), 1, dtype=np.float32)
        c_matrix = params.get_c_matrix()
        for i in [0, 1, 2]:
            pref_matrix[:, i] = c_matrix[trait_vec, i]
        return pref_matrix

    def disperse(self, params):
        disp_dict = dispersal_models.dispersal_model_dict
        if params.dispersal_model in disp_dict:
            delta = disp_dict[params.dispersal_model](self, params)
        else:
            raise Exception("Dispersal model '%s' is invalid!" %
                            params.dispersal_model)
        edge_model_dict = {"closed" : self.closed, "flux" : self.flux,
                           "ring" : self.ring}
        if params.edge_model in edge_model_dict:
            edge_model_dict[params.edge_model](delta)
        else:
            raise Exception("Edge model '%s' is invalid!" % params.edge_model)

    def closed(self, delta):
        """Set the displacement of any individual who would exit the space when
        displacements are applied to 0, freezing them in place
        """
        positions = delta + self.get_x()
        delta[positions < 0] = 0
        delta[positions > 1] = 0
        self.arr[:, self._x] += delta

    def flux(self, delta, params):
        self.arr[:, self._x] += delta
        t = self.t
        exits = self.detect_exits()
        self.set_flags(exits, -3)
        left_x = dispersal_models.draw_migrants(params)
        left_migrants, runlog = Generation.get_migrants(left_x, 1, t, params)
        right_x = 1 - dispersal_models.draw_migrants(params)
        right_migrants, runlog = Generation.get_migrants(right_x, 2, t, params)
        migrants = Generation.merge(left_migrants, right_migrants)
        self = Generation.merge(self, migrants)
        # no idea if this works lol

    def ring(self, delta):
        """An experimental edge function where individuals who exit the space
        are deposited onto the other side of space, creating a closed loop
        """
        self.arr[:, self._x] += delta
        self.arr[self.detect_l_exits(), self._x] += 1
        self.arr[self.detect_r_exits(), self._x] -= 1

    def detect_l_exits(self):
        """Return an index of left exits"""
        return np.where(self.arr[:, self._x] < 0)[0]

    def detect_r_exits(self):
        """Return an index of right exits"""
        return np.where(self.arr[:, self._x] > 1)[0]

    def detect_exits(self):
        """Return the indices of individuals with invalid x coordinates outside
        [0, 1]
        """
        return np.concatenate((self.detect_l_exits(), self.detect_l_exits))

    def fitness(self, params):
        if params.intrinsic_fitness:
            fitness_models.intrinsic_fitness(self, params)
        if params.extrinsic_fitness:
            fitness_models.extrinsic_fitness(self, params)

    @staticmethod
    def compute_bounds(seeking_sex, target_sex, limits):
        """Compute bounds, given two arrays as arguments"""
        x_0 = seeking_sex[:, FullPedigree._x]
        x_1 = target_sex[:, FullPedigree._x]
        l_bound = np.searchsorted(a = x_1, v = x_0 + limits[0])
        r_bound = np.searchsorted(a = x_1, v = x_0 + limits[1])
        bounds = np.column_stack((l_bound, r_bound))
        return bounds

    def compute_sex_bounds(self, seeking_i, target_i, limits):
        """Compute bounds, given two integers representing sexes as args"""
        idx_0 = self.get_sex_idx(seeking_i)
        idx_1 = self.get_sex_idx(target_i)
        x_0 = self.get_x()[idx_0]
        x_1 = self.get_x()[idx_1]
        l_bound = np.searchsorted(a = x_1, v = x_0 + limits[0])
        r_bound = np.searchsorted(a = x_1, v = x_0 + limits[1])
        bounds = np.column_stack((l_bound, r_bound))
        return bounds

    def get_signal_props(self, limits):
        """Compute the proportion of same-signal males within a spatial limit
        for each male in a generation.

        Used to adjust the direction or scale of male dispersal under nonrandom
        dispersal models.
        """
        bounds = self.compute_sex_bounds(1, 1, limits)
        if limits[0] != 0 and limits[1] != 0:
            self_counting = True
        else:
            self_counting = False
        n = bounds[:, 1] - bounds[:, 0]
        if self_counting:
            n -= 1
        idx11, idx12, idx22 = self.get_male_signal_indices()
        signal_props = np.zeros(self.get_n_males(), dtype = np.float32)
        signal_props[idx11] = (
                np.searchsorted(idx11, bounds[idx11, 1])
              - np.searchsorted(idx11, bounds[idx11, 0]))
        signal_props[idx22] = (
                np.searchsorted(idx22, bounds[idx22, 1])
              - np.searchsorted(idx22, bounds[idx22, 0]))
        if self_counting:
            signal_props -= 1
        signal_props /= n
        signal_props[np.isnan(signal_props)] = 1
        return signal_props, idx12

    def get_male_signal_sums(self):
        """Return the sum of signal alleles for males only"""
        males = self.get_males()
        return np.sum(males[:, self._A_loci], axis = 1)

    def get_male_signal_indices(self):
        signal_sums = self.get_male_signal_sums()
        idx11 = np.where(signal_sums == 2)[0]
        idx12 = np.where(signal_sums == 3)[0]
        idx22 = np.where(signal_sums == 4)[0]
        return idx11, idx12, idx22

    def get_sex_indices(self):
        """Return the indices of females and of males in a generation
        """
        f_idx = np.where(self.arr[:, self._sex] == 0)[0]
        m_idx = np.where(self.arr[:, self._sex] == 1)[0]
        return f_idx, m_idx

    def sort_by_x(self):
        """Sort the generation by x coordinate. Sorting is vital to the
        correct operation of many Generation functions
        """
        x = self.get_x()
        self.arr = self.arr[x.argsort()]

    def sort_by_x_and_id(self, i0):
        """Sort the generation by x coordinate and enter the id column, where
        each element matches the index of its row. This may seem redundant
        but it is convenient for sampling sub-pedigrees. i1 is return to the
        Trial object to keep track of the index
        """
        self.sort_by_x()
        n = self.get_n_organisms()
        i1 = i0 + n
        ids = np.arange(i0, i1)
        self.arr[:, self._id] = ids
        return i1

    def remove_dead(self):
        """Delete individuals with flag != 1 or 0. Counterintuitively,
        individuals with flag = 0 are retained; this is because of the order
        in which functions ar currently executed in the main loop
        """
        self.arr = np.delete(self.arr, self.get_dead_idx(), axis=0)

    def plot_subpops(self):
        gen_subpop_arr = SubpopArr.from_generation(self)
        fig = gen_subpop_arr.plot_density()
        return fig

    def plot_allele_freqs(self):
        gen_allele_arr = AlleleArr.from_generation(self)
        fig = gen_allele_arr.plot_freq()
        return fig


class MatingPairs(FullPedigree):
    organism_axis = 0
    sex_axis = 1
    character_axis = 2
    _mat_alleles = [0, 2]
    _pat_alleles = [1, 3]

    def __init__(self, generation, params):
        self.n = None
        self.pair_ids = self.compute_pair_ids(generation, params)
        arr = self.get_mating_pairs(generation)
        super().__init__(arr, params)

    def initialize_pair_ids(self, n_offspring):
        self.n = np.sum(n_offspring)
        mating_pair_ids = np.zeros((self.n, 2), dtype=np.int32)
        return mating_pair_ids

    @staticmethod
    def interpret_mating_fxn(params):
        if params.mating_model == "gaussian":
            fxn = mating_models.gaussian
        elif params.mating_model == "uniform":
            fxn = mating_models.uniform
        elif params.mating_model == "unbounded":
            fxn = mating_models.unbounded
        else:
            print("invalid mating function")
            fxn = None
        return fxn

    def __len__(self):
        """Return the number of per offspring pairings in the array"""
        return len(self.arr)

    def __getitem__(self, i):
        """Get the pairing at index i"""
        return self.arr[i, :, :]

    def compute_pair_ids(self, generation, params):
        fxn = self.interpret_mating_fxn(params)
        m_x_vec = generation.get_male_x()
        f_x_vec = generation.get_female_x()
        pref_matrix = generation.compute_pref_matrix(params)
        pref_vec_idx = generation.compute_pref_idx()
        n_offspring = generation.compute_n_offspring(params)
        b = params.bound
        bounds = generation.compute_sex_bounds(0, 1, [-b, b])
        pair_ids = self.initialize_pair_ids(n_offspring)
        n_females = generation.get_n_females()
        i = 0
        for f_id in np.arange(n_females):
            if n_offspring[f_id] > 0:
                x = f_x_vec[f_id]
                m_id = fxn(x, m_x_vec, pref_matrix[:, pref_vec_idx[f_id]],
                    bounds[f_id], params)
                pair_ids[i:i + n_offspring[f_id]] = [f_id, m_id]
                i += n_offspring[f_id]
            else:
                pass
        return pair_ids

    def get_mating_pairs(self, generation):
        """Uses the mating_id_arr to organize a 3d array containing each
        parent's pedigree entry explicitly.
        """
        arr = np.zeros((len(self.pair_ids), 2, self.n_cols))
        females, males = generation.sex_split()
        arr[:, 0, :] = females[self.pair_ids[:, 0]]
        arr[:, 1, :] = males[self.pair_ids[:, 1]]
        return arr

    def get_zygotes(self):
        """Use the self.get_gametes to randomly draw gametes from parents and
        combine them in a pre-initialized array to get an array of alleles.
        This array is used to designate alleles for the child generation
        """
        zygotes = np.zeros((self.n, self.n_alleles), dtype=self.dtype)
        zygotes[:, self._mat_alleles] = self.get_gametes(0)
        zygotes[:, self._pat_alleles] = self.get_gametes(1)
        return zygotes

    def get_gametes(self, sex):
        idx0 = np.arange(self.n)
        A_idx = np.random.randint(0, 2, size=self.n) + self._A_loc0
        B_idx = np.random.randint(0, 2, size=self.n) + self._B_loc0
        gametes = np.zeros((self.n, 2), dtype=self.dtype)
        gametes[:, 0] = self.arr[idx0, sex, A_idx]
        gametes[:, 1] = self.arr[idx0, sex, B_idx]
        return gametes

    def get_parent_ids(self):
        return self.arr[:, :, self._id]

    def get_maternal_x(self):
        return self.arr[:, 0, self._x]


class Pedigree(FullPedigree):

    adjust_fac = 1.01

    def __init__(self, arr, params, max = None):
        super().__init__(arr, params)
        self.g = params.g
        self.t = params.g
        self.max = max

    @classmethod
    def new(cls, params):
        max = int(params.K * (params.g + 1) * cls.adjust_fac)
        arr = np.zeros((max, cls.n_cols), dtype=cls.dtype)
        return cls(arr, params, max)

    @classmethod
    def load_txt(cls, filename):
        file = open(filename, 'r')
        string = file.readline()
        params = Params.from_string(string)
        arr = np.loadtxt(file, dtype=np.float32)
        file.close()
        return cls(arr, params)

    def __repr__(self):
        return (f"Pedigree with size {self.get_n_organisms()} in {self.g + 1} "
                "generations")

    def save_txt(self, filename):
        """Save the pedigree array as a .txt document with the params
        attribute as a string header
        """
        header = (str(vars(self.params)))
        file = open(filename, 'w')
        np.savetxt(file, self.arr, fmt="%d %d %1.8f %d %d %d %d %d %d %d %d",
                   delimiter=' ', newline='\n', header=header)
        file.close()
        print(f"pedigree saved at {filename}")

    def save_ped(self, filename):
        """Save the pedigree array using the .ped format and an associated
        .dat file to hold parameters and provenance
        """
        fmt = "% 4d % 11d %12.7f % 9d % 11d % 11d % 7d % 5d % 7d % 5d % 7d"
        header = ("sex         id            x         t    maternal    "
                  "paternal      A0    A1      B0    B1    flag")
        pedigree_file = open(filename, 'w')
        np.savetxt(pedigree_file, self.arr, fmt=fmt, delimiter=' ',
                   newline='\n', header=header)
        pedigree_file.close()
        print(f"pedigree saved at {filename}")

    def enter_gen(self, generation, i0, i1, flag=0):
        if i1 > self.max:
            self.expand()
        generation.set_all_flags(flag)
        self.insert_gen(generation, i0, i1)
        self.t = generation.t

    def insert_gen(self, generation, i0, i1):
        self.arr[i0:i1, :] = generation.arr

    def expand(self):
        """expand the pedigree to accommodate more organisms"""
        g_elapsed = self.g - self.t
        avg_util = int(self.max / g_elapsed)
        new_max = int(avg_util * self.t * self.adjust_fac)
        aux_arr = np.zeros((new_max, self.n_cols), dtype=self.dtype)
        self.arr = np.vstack((self.arr, aux_arr))
        self.max += new_max
        print("pedigree arr expanded " + str(new_max)
              + " rows at est. utilization " + str(avg_util))

    def trim(self, i1):
        """trim the pop array of unfilled rows"""
        self.arr = self.arr[:i1]
        excess = self.max - i1
        frac = np.round((1 - excess / self.max) * 100, 2)
        print("pedigree trimmed of " + str(excess) + " excess rows, "
              + str(frac) + "% utilization")

    def get_gen_arr(self, t):
        """Return a naked array of the generation at time t"""
        return self.arr[np.where(self.arr[:, self._t] == t)[0]]

    def get_generation(self, t):
        """Reconstruct a Generation instance for all the organisms with time
        coordinate t"""
        gen = self.get_gen_arr(t)
        n = len(gen)
        generation = Generation(n, gen[:, self._x], t, gen[:, self._parents],
                                gen[:, self._alleles], self.params)
        generation.arr[:, self._id] = gen[:, self._id]
        return generation

    def get_n_organisms_at_t(self, t):
        """Return the number of organisms in generation t"""
        return np.size(np.where(self.arr[:, self._t] == t)[0])

    def get_gen_idx(self, t):
        """Return the index of all organisms in generation t"""
        return np.where(self.arr[:, self._t] == t)[0]

    def compute_ancestry(self, t = 0):
        """Compute the genealogical ancestry values of the individuals living
        at generation t
        """
        n = self.get_n_organisms()
        anc = np.zeros((n, 3), dtype=np.float32)
        parents = self.arr[:, self._parents].astype(np.int32)
        founders = self.get_gen_idx(self.g)
        anc[founders, :2] = parents[founders]
        anc[founders, 2] = self.arr[founders, self._A_loc0] - 1
        gen_idx = None
        for i in np.arange(self.g - 1, t - 1, -1):
            gen_idx = self.get_gen_idx(i)
            gen_parents = parents[gen_idx]
            anc[gen_idx, :2] = gen_parents
            anc[gen_idx, 2] = np.mean([anc[gen_parents[:, 0], 2],
                                       anc[gen_parents[:, 1], 2]], axis=0)
        ancs = anc[gen_idx, 2]
        return ancs

    def get_subpop_ancestries(self):
        pass

    def get_idx_between_t(self, t_min, t_max):
        """Return the indexes at which t is greater than or equal to t_min
        and less than or equal to t_max
        """
        t = self.get_t()
        return np.where((t >= t_min) & (t <= t_max))[0]


class AbbrevPedigree(PedigreeLike):
    """Abbreviated to only the bare minimum information to run coalescence
    simulations. Id matches row index and is therefore strictly unnecessary
    """
    dtype = np.int32
    n_cols = 5
    _id = 0
    _t = 1
    _mat_id = 2
    _pat_id = 3
    _subpop_code = 4
    _parents = [2, 3]
    map = np.array([1, 3, 4, 5])

    def __init__(self, arr, params, max = None):
        super().__init__(arr, params)
        self.g = params.g
        self.t = params.g
        self.founding_gen = None
        self.last_gen = None
        if max:
            self.max = max

    @classmethod
    def new(cls, params):
        max = int(params.K * (params.g + 1) * cls.adjust_fac)
        arr = np.zeros((max, cls.n_cols), dtype=cls.dtype)
        return cls(arr, params, max)

    @classmethod
    def load_txt(cls, filename):
        file = open(filename, 'r')
        string = file.readline()
        params = Params.from_string(string)
        arr = np.loadtxt(file, dtype=np.float32)
        file.close()
        return cls(arr, params)

    def __len__(self):
        """Return the number of organisms in self.arr"""
        return len(self.arr)

    def save_txt(self, filename):
        """Save the pedigree array as a .txt document with the params
        attribute as a string header
        """
        header = (str(vars(self.params)))
        file = open(filename, 'w')
        np.savetxt(file, self.arr, fmt="%d %d %d %d", delimiter=' ',
                   newline='\n', header=header)
        # founding and final generations are not currently saved with the arr
        file.close()
        print(f"pedigree saved at {filename}")

    def save_first_gen(self, generation):
        """Save the founding generation so that the initial state is known"""
        self.founding_gen = generation

    def enter_gen(self, generation, i0, i1):
        """Record a Generation instance in the pedigree after flagging it
        with 'flag'
        """
        if i1 > self.max:
            self.expand()
        self.insert_gen(generation, i0, i1)
        self.t = generation.t

    def insert_gen(self, generation, i0, i1):
        self.arr[i0:i1, :self._subpop_code] = generation.arr[:, self.map]
        self.arr[i0:i1, self._subpop_code] = generation.get_subpop_idx()

    def expand(self):
        """expand the pedigree to accommodate more organisms"""
        g_elapsed = self.g - self.t
        avg_util = int(self.max / g_elapsed)
        new_max = int(avg_util * self.t * self.adjust_fac)
        aux_arr = np.zeros((new_max, self.n_cols), dtype=self.dtype)
        self.arr = np.vstack((self.arr, aux_arr))
        self.max += new_max
        print("pedigree arr expanded " + str(new_max)
              + " rows at est. utilization " + str(avg_util))

    def save_last_gen(self, generation):
        """Save the final gen, so that spatial sampling etc. is possible"""
        self.last_gen = generation

    def trim(self, i1):
        """trim the pop array of unfilled rows"""
        self.arr = self.arr[:i1]
        excess = self.max - i1
        frac = np.round((1 - excess / self.max) * 100, 2)
        print("pedigree trimmed of " + str(excess) + " excess rows, "
              + str(frac) + "% utilization")

    def get_gen_arr(self, t):
        return self.arr[np.where(self.arr[:, self._t] == t)[0]]

    def get_idx_at_t(self, t):
        """Return the indices at which organisms from time t exist"""
        return np.where(self.arr[:, self._t] == t)

    def get_min_gen_0_id(self):
        """Return the index of the first organism in generation 0"""
        t0_idx = self.get_idx_at_t(t=0)
        return np.min(t0_idx)

    def get_parents(self):
        """Return the two parent id columns of the array"""
        return self.arr[:, self._parents]

    def get_subpops(self):
        """Return the genotype code column"""
        return self.arr[:, self._subpop_code]

    def get_t(self):
        """Return the time column"""
        return self.arr[:, self._t]


class SubpopArr:
    time_axis = 0
    space_axis = 1
    subpop_axis = 2

    def __init__(self, arr, params, t_now, bin_size):
        self.arr = arr
        self.params = params
        self.t = t_now
        self.bin_size = bin_size
        self.g = params.g

    @classmethod
    def initialize(cls, params, bin_size=0.01):
        n_bins = get_n_bins(bin_size)
        t_dim = params.g + 1
        arr = np.zeros((t_dim, n_bins, PedigreeLike.n_subpops), dtype=np.int32)
        return cls(arr, params, t_dim, bin_size)

    @classmethod
    def from_generation(cls, generation, bin_size=0.01):
        """Get a SubpopArr of time dimension 1, recording a single generation
        """
        bin_edges, n_bins = get_bins(bin_size)
        n_subpops = generation.n_subpops
        arr = np.zeros((1, n_bins, n_subpops), dtype=np.int32)
        x = generation.get_x()
        subpop_idx = generation.get_subpop_idx()
        for i in np.arange(n_subpops):
            arr[0, :, i] = np.histogram(x[subpop_idx == i], bins=bin_edges)[0]
        params = generation.params
        t = generation.t
        return cls(arr, params, t, bin_size)

    @classmethod
    def from_pedigree(cls, pedigree, bin_size=0.01):
        """Get a SubpopArr recording population densities in a Pedigree of
        time dimension pedigree.g + 1
        """
        n_bins = get_n_bins(bin_size)
        t_dim = pedigree.g + 1
        arr = np.zeros((t_dim, n_bins, pedigree.n_subpops), dtype=np.int32)
        for t in np.arange(pedigree.g + 1):
            generation = pedigree.get_generation(t)
            arr[t, :, :] = SubpopArr.from_generation(generation).arr[0]
        params = pedigree.params
        t_now = 0
        return cls(arr, params, t_now, bin_size)

    @classmethod
    def load_txt(cls, filename):
        file = open(filename, 'r')
        string = file.readline()
        params = Params.from_string(string)
        raw_arr = np.loadtxt(file, dtype=np.int32)
        file.close()
        shape = np.shape(raw_arr)
        t_dim = shape[0]
        n_subpops = PedigreeLike.n_subpops
        bin_size = shape[1] // n_subpops
        new_shape = (t_dim, bin_size, n_subpops)
        arr = np.reshape(raw_arr, new_shape)
        t_now = 0
        return cls(arr, params, t_now, bin_size)

    def __str__(self):
        """Return a description of the SubpopArr instance"""
        return f"SubpopArr of size {len(self)} over {self.g + 1} generations"

    def __len__(self):
        """Return the number of generations recorded in the SubpopArr"""
        return np.shape(self.arr)[0]

    def __getitem__(self, idx):
        """Return the generation/s represented at idx"""
        return self.arr[idx]

    def enter_generation(self, generation):
        t = generation.t
        self.arr[t, :, :] = SubpopArr.from_generation(generation).arr[0]

    def save_txt(self, filename):
        """Reshape the array such that it's 2d and save it as a .txt file"""
        shape = np.shape(self.arr)
        reshaped = self.arr.reshape(shape[0], shape[1] * shape[2])
        file = open(filename, 'w')
        header = str(vars(self.params))
        np.savetxt(file, reshaped, delimiter=' ', newline='\n', header=header,
                   fmt="%1.1i")
        file.close()
        print("SubpopArr saved at " + filename)

    def get_size(self):
        """Return the total number of organisms recorded in the array"""
        return np.sum(self.arr)

    def get_generation_populations(self):
        """Return a vector of the whole populations of each generation"""
        return np.sum(np.sum(self.arr, axis=1), axis=1)

    def get_generation_population(self, t):
        """Return the whole-population size at generation t"""
        return np.sum(self.arr[t])

    def get_hybrid_densities(self, t):
        """Compute the sum of densities of the subpopulations with one or more
        heterozygous loci at generation t
        """
        return np.sum(self.arr[t, :, 1:8], axis=1)

    def get_bin_densities(self, t):
        """Return a vector of whole population bin densities in generation t"""
        return np.sum(self.arr[t], axis=1)

    def plot_density(self, t=0):
        """Make a plot of the densities of each subpopulation across space
        at index (time) t"""
        fig = plt.figure(figsize=Const.plot_size)
        sub = fig.add_subplot(111)
        b = get_bin_mids(self.bin_size)
        n_vec = self.get_bin_densities(t)
        sub.plot(b, n_vec, color="black", linestyle='dashed', linewidth=2)
        sub.plot(b, self.get_hybrid_densities(t), color='green',
                 linestyle='dashed', linewidth=2)
        c = Const.subpop_colors
        for i in np.arange(9):
            sub.plot(b, self.arr[t, :, i], color=c[i], linewidth=2)
        y_max = self.params.K * 1.3 * Const.bin_size
        n = str(self.get_generation_population(t))
        if len(self) == 1:
            time = self.t
        else:
            time = t
        title = "t = " + str(time) + " n = " + n
        sub = plot_util.setup_space_plot(sub, y_max, "subpop density", title)
        plt.legend(["N", "Hyb"] + Const.subpop_legend, fontsize=8,
                   bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
        fig.show()
        return fig

    def plot_history(self, log=True):
        n_vec = self.get_generation_populations()
        fig = plt.figure(figsize=(8, 6))
        sub = fig.add_subplot(111)
        times = np.arange(self.g + 1)
        sub.plot(times, n_vec, color="black")
        for i in np.arange(9):
            sub.plot(times, np.sum(self.arr[:, :, i], axis=1),
                     color=Const.subpop_colors[i], linewidth=2)
        sub.set_xlim(0, np.max(times))
        sub.invert_xaxis()
        if log:
            sub.set_yscale("log")
        else:
            y_lim = np.round(self.params.K * 1.1)
            sub.set_ylim(0, y_lim)
        sub.set_xlabel("t before present")
        sub.set_ylabel("population size")
        sub.legend(["N"] + Const.subpop_legend, fontsize=8)
        fig.show()


class ClinePars:

    def __init__(self, x_vec, k_vec, params, bin_size):
        if len(x_vec) != len(k_vec):
            raise AttributeError("x and k vector lengths do not match")
        self.x_vec = x_vec
        self.k_vec = k_vec
        self.params = params
        self.bin_size = bin_size

    @classmethod
    def from_subpop_arr(cls, subpop_arr):
        allele_arr = AlleleArr.from_subpop_arr(subpop_arr)
        return cls.from_allele_arr(allele_arr)

    @classmethod
    def from_allele_arr(cls, allele_arr):
        allele_freq = allele_arr.get_freq()
        a2_freq = allele_freq[:, :, 0, 1]
        x = get_bin_mids(allele_arr.bin_size)
        params = allele_arr.params
        t_dim = params.g + 1
        x_vec = np.zeros(t_dim)
        k_vec = np.zeros(t_dim)
        for t in np.arange(t_dim):
            try:
                cline_opt = cls.optimize_logistic(x, a2_freq[t])
                k_vec[t] = cline_opt[0][0]
                x_vec[t] = cline_opt[0][1]
            except:
                k_vec[t] = -1
                x_vec[t] = -1
        bin_size = allele_arr.bin_size
        return cls(x_vec, k_vec, params, bin_size)

    def __len__(self):
        return len(self.x_vec)

    @staticmethod
    def logistic_fxn(x, k, x_0):
        return 1 / (1.0 + np.exp(-k * (x - x_0)))

    @classmethod
    def optimize_logistic(cls, x, y):
        return opt.curve_fit(cls.logistic_fxn, x, y)

    def plot(self):
        length = len(self)
        t = np.arange(length)
        fig, axs = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
        x_ax, k_ax = axs[0], axs[1]
        k_ax.plot(t, self.k_vec, color="black", linewidth=2)
        x_ax.plot(t, np.full(length, 0.5), color="red", linestyle="dashed")
        x_ax.plot(t, self.x_vec, color="black", linewidth=2)
        k_ax.set_ylim(0, 200)
        x_ax.set_ylim(0, 1)
        k_ax.set_xlim(0, length)
        axs[1].set_xlabel("generations before present")
        x_ax.set_ylabel("x_0")
        k_ax.set_ylabel("k")
        x_ax.set_title("cline parameter x_0")
        k_ax.set_title("cline parameter k")
        x_ax.invert_xaxis()
        fig.suptitle("Cline Parameters")
        fig.tight_layout(pad=1.0)
        fig.show()

    def plot_clines(self, n=10):
        """Plot the cline approximation at n even intervals in time"""
        snaps = np.linspace(len(self) - 1, 0, n, dtype=np.int32)
        x = get_bin_mids(self.bin_size)
        fig = plt.figure(figsize=(8, 6))
        sub = fig.add_subplot(111)
        colors = matplotlib.cm.YlGnBu(np.linspace(0.2, 1, n))
        for i in np.arange(n):
            t = snaps[i]
            y = self.logistic_fxn(x, self.k_vec[t], self.x_vec[t])
            sub.plot(x, y, color=colors[i], linewidth=2)
        sub = plot_util.setup_space_plot(sub, 1.01, "$A^2$ cline", "Clines")
        sub.legend(snaps)
        fig.show()


class AlleleArr:
    time_axis = 0
    space_axis = 1
    locus_axis = 2
    allele_axis = 3

    def __init__(self, arr, params, t_now, bin_size):
        self.arr = arr
        self.params = params
        self.t = t_now
        self.bin_size = bin_size

    @classmethod
    def from_generation(cls, generation, bin_size=0.01):
        """Get an AlleleArr of time dimension 1, recording the allele
        distribution in a single Generation
        """
        x = generation.get_x()
        bins, n_bins = get_bins(0.01)
        alleles = generation.get_alleles()
        loci = np.array([[0, 1], [0, 1], [2, 3], [2, 3]])
        arr = np.zeros((1, n_bins, 2, 2))
        for i in np.arange(4):
            j, k = np.unravel_index(i, (2, 2))
            a = i % 2 + 1
            arr[0, :, j, k] = (
                np.histogram(x[alleles[:, loci[i, 0]] == a], bins)[0]
                + np.histogram(x[alleles[:, loci[i, 1]] == a], bins)[0])
        params = generation.params
        t = generation.t
        return cls(arr, params, t, bin_size)

    @classmethod
    def from_pedigree(cls, pedigree, bin_size=0.01):
        t_dim = pedigree.g + 1
        arr = np.zeros((t_dim, Const.n_bins, 2, 2), dtype=np.int32)
        for t in np.arange(t_dim):
            generation = pedigree.get_generation(t)
            arr[t, :, :, :] = AlleleArr.from_generation(generation).arr
        params = pedigree.params
        t_now = pedigree.t
        return cls(arr, params, t_now, bin_size)

    @classmethod
    def from_subpop_arr(cls, subpop_arr):
        """Convert data from a SubpopArr into an AlleleArr"""
        fac = Const.allele_manifold
        arr = np.sum(subpop_arr.arr[:, :, :, None, None] * fac, axis=2)
        params = subpop_arr.params
        t = subpop_arr.t
        bin_size = subpop_arr.bin_size
        return cls(arr, params, t, bin_size)

    def __str__(self):
        return (f"AlleleArr holding {self.get_n_alleles()} alleles from "
                f"{self.get_n_organisms()} organisms over {len(self)}" 
                "generations")

    def __len__(self):
        """Return the number of generations represented in the array"""
        return np.shape(self.arr)[0]

    def get_n_alleles(self):
        """Return the total number of alleles held in the array"""
        return np.sum(self.arr)

    def get_n_organisms(self):
        """Return the total number of organisms represented in the array"""
        return np.sum(self.arr) // 4

    def get_n_at_t(self, t):
        """Return the population size of generation t"""
        return np.sum(self.arr[t]) // 4

    def get_bin_n(self):
        """Return a vector holding the number of loci represented in each
        spatial bin
        """
        return np.sum(self.arr, axis=3)

    def get_bin_n_at_t(self, t):
        """Return a vector holding the number of loci represented in each
        spatial bin at time t
        """
        return np.sum(self.arr[t, :, :, :], axis=2)

    def get_freq(self):
        """Return an array of allele frequencies"""
        n_loci = self.get_bin_n()
        return self.arr / n_loci[:, :, :, np.newaxis]

    def get_freq_at_t(self, t):
        """Return an array of allele frequencies at time t"""
        n_loci = self.get_bin_n()
        return self.arr[t] / n_loci[t, :, :, np.newaxis]

    def plot_freq(self, t=0):
        fig = plt.figure(figsize=Const.plot_size)
        sub = fig.add_subplot(111)
        freqs = self.get_freq_at_t(t)
        bin_mids = get_bin_mids(self.bin_size)
        for i in np.arange(3, -1, -1):
            j, k = np.unravel_index(i, (2, 2))
            sub.plot(bin_mids, freqs[:, j, k],
                     color=Const.allele_colors[i], linewidth=2,
                     label=Const.allele_legend[i])
        title = "t = " + str(self.t) + " n = " + str(self.get_n_at_t())
        sub = plot_util.setup_space_plot(sub, 1.01, "allele freq", title)
        plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0)
        fig.show()
        return fig


class RaggedArr3d:
    """Class to hold a ragged set of vectors in nested lists"""

    def __init__(self, shape):
        """shape must be a tuple of size 2"""
        self.shape = shape
        self.arr = [[np.array([], dtype=np.float32)
                            for j in np.arange(shape[1])]
                           for i in np.arange(shape[0])]

    def enter_vec(self, vec, i, j):
        """Enter a vector at coords (i, j)"""
        self.arr[i][j] = vec

    def get_statistics(self):
        self.means = np.zeros(self.shape, dtype=np.float32)
        self.stds = np.zeros(self.shape, dtype=np.float32)
        self.sums = np.zeros(self.shape, dtype=np.float32)
        for i in np.arange(self.shape[0]):
            for j in np.arange(self.shape[1]):
                if len(self.arr[i][j] > 0):
                    self.means[i, j] = np.mean(self.arr[i][j])
                    self.stds[i, j] = np.std(self.arr[i][j])
                self.sums[i, j] = np.sum(self.arr[i][j])

    def get_n_elements(self):
        length = 0
        for i in np.arange(self.shape[0]):
            for j in np.arange(self.shape[1]):
                length += len(self.arr[i][j])
        return length


class MatingHistograms:
    """Kind of a messed up class. Centered on two large arrays of dimensions
    (subpop, sex, x_bin, histogram) which hold histograms of reproductive success
    across space and time
    """
    n_fecundity_bins = 20
    n_pairing_bins = 10

    def __init__(self, n_arr, pairing_hist, fecundity_hist, female_pairing_arr,
                 male_pairing_arr, female_fecundity_arr, male_fecundity_arr,
                 params, bin_size):
        self.n_arr = n_arr
        self.pairing_hist = pairing_hist
        self.fecundity_hist = fecundity_hist
        self.female_pairing_arr = female_pairing_arr
        self.male_pairing_arr = male_pairing_arr
        self.female_fecundity_arr = female_fecundity_arr
        self.male_fecundity_arr = male_fecundity_arr
        self.params = params
        self.bin_size = bin_size
        self.bin_mids = np.arange(bin_size/2, 1 + bin_size/2, bin_size)

    @classmethod
    def from_pedigree(cls, pedigree, bin_size = 0.02):
        """Get the histograms via analysis of a pedigree. Computes histograms
        """
        g = pedigree.params.g
        female_ids = pedigree.get_female_idx()
        male_ids = pedigree.get_male_idx()
        t = pedigree.get_t()
        female_t = t[female_ids]
        male_t = t[male_ids]
        female_ids = female_ids[female_t > 0]
        male_ids = male_ids[male_t > 0]
        max_founder_id = np.max(pedigree.get_gen_idx(g))
        pairings = pedigree.get_parents()[max_founder_id + 1:]
        mat_ids = np.sort(pairings[:, 0])
        pat_ids = np.sort(pairings[:, 1])
        female_fecundity = (np.searchsorted(mat_ids, female_ids + 1)
                              - np.searchsorted(mat_ids, female_ids))
        male_fecundity = (np.searchsorted(pat_ids, male_ids + 1)
                            - np.searchsorted(pat_ids, male_ids))
        unique_pairings = np.unique(pairings, axis=0)
        unique_mat = np.sort(unique_pairings[:, 0])
        unique_pat = np.sort(unique_pairings[:, 1])
        female_pairings = (np.searchsorted(unique_mat, female_ids + 1)
                            - np.searchsorted(unique_mat, female_ids))
        male_pairings = (np.searchsorted(unique_pat, male_ids + 1)
                          - np.searchsorted(unique_pat, male_ids))
        subpop_idx = pedigree.get_subpop_idx()
        female_subpop_idx = subpop_idx[female_ids]
        male_subpop_idx = subpop_idx[male_ids]
        x = pedigree.get_x()
        x_bins = np.arange(0, 1, bin_size)
        n_bins = len(x_bins)
        female_x_idx = np.searchsorted(x_bins, x[female_ids]) - 1
        male_x_idx = np.searchsorted(x_bins, x[male_ids]) - 1
        fecundity_bins = np.arange(cls.n_fecundity_bins + 1)
        n_pops = pedigree.n_subpops
        fecundity_hist = np.zeros((n_pops, 2, n_bins, cls.n_fecundity_bins))
        pairing_bins = np.arange(cls.n_pairing_bins + 1)
        pairing_hist = np.zeros((n_pops, 2, n_bins, cls.n_pairing_bins))
        n_arr = np.zeros((n_pops, 2, n_bins))

        bin_females = []
        bin_males = []
        for j in np.arange(n_bins):
            bin_females.append(np.where(female_x_idx == j))
            bin_males.append(np.where(male_x_idx == j))

        shape = (n_pops, n_bins)
        female_pairing_arr = RaggedArr3d(shape)
        male_pairing_arr = RaggedArr3d(shape)
        female_fecundity_arr = RaggedArr3d(shape)
        male_fecundity_arr = RaggedArr3d(shape)

        for i in np.arange(n_pops):
            subpop_females = np.where(female_subpop_idx == i)
            subpop_males = np.where(male_subpop_idx == i)
            for j in np.arange(n_bins):
                f_idx = np.intersect1d(bin_females[j], subpop_females)
                m_idx = np.intersect1d(bin_males[j], subpop_males)

                female_pairing_arr.enter_vec(female_pairings[f_idx], i, j)
                male_pairing_arr.enter_vec(male_pairings[m_idx], i, j)
                female_fecundity_arr.enter_vec(female_fecundity[f_idx], i, j)
                male_fecundity_arr.enter_vec(male_fecundity[m_idx], i, j)

                fecundity_hist[i, 0, j, :] = np.histogram(
                    female_fecundity[f_idx], bins=fecundity_bins)[0]
                fecundity_hist[i, 1, j, :] = np.histogram(
                    male_fecundity[m_idx], bins=fecundity_bins)[0]
                pairing_hist[i, 0, j, :] = np.histogram(
                    female_pairings[f_idx], bins=pairing_bins)[0]
                pairing_hist[i, 1, j, :] = np.histogram(
                    male_pairings[m_idx], bins=pairing_bins)[0]
                n_arr[i, 0, j] = len(f_idx)
                n_arr[i, 1, j] = len(m_idx)
        return cls(n_arr, pairing_hist, fecundity_hist, female_pairing_arr,
                 male_pairing_arr, female_fecundity_arr, male_fecundity_arr,
                 pedigree.params, bin_size)

    def get_statistics(self):
        self.female_pairing_arr.get_statistics()
        self.male_pairing_arr.get_statistics()
        self.female_fecundity_arr.get_statistics()
        self.male_fecundity_arr.get_statistics()

        self.pairing_statistics()
        self.fecundity_statistics()

        self.plot_pairing_statistics()
        self.plot_pairing_heatmap()
        #self.plot_fecundity_statistics()
        #self.fecundity_heatmap()

    def pairing_statistics(self):
        nonzeros = np.nonzero(self.pairing_hist)
        self.norm_pairings = np.copy(self.pairing_hist)
        self.norm_pairings[nonzeros] = self.norm_pairings[nonzeros] / \
                                  self.n_arr[nonzeros[:3]]
        pairing_bins = np.arange(self.n_pairing_bins)
        self.mean_pairings = np.sum(self.norm_pairings * pairing_bins, axis=3)

    def fecundity_statistics(self):
        nonzeros = np.nonzero(self.fecundity_hist)
        self.norm_fecundity = np.copy(self.fecundity_hist)
        self.norm_fecundity[nonzeros] = self.norm_fecundity[nonzeros] / \
                                  self.n_arr[nonzeros[:3]]
        fecundity_bins = np.arange(self.n_fecundity_bins)
        self.mean_fecundity = np.sum(self.norm_fecundity * fecundity_bins,
                                     axis=3)

    def plot_pairing_statistics(self):
        fig, axs = plt.subplots(3, 3, figsize=(13, 10))
        for i in np.arange(PedigreeLike.n_subpops):
            ax = axs[np.unravel_index(i, (3, 3))]
            color = colors.to_rgb(Const.subpop_colors[i])
            femcolor = [c * 0.5 for c in color]
            ax.errorbar(self.bin_mids, self.female_pairing_arr.means[i, :],
                        yerr=self.female_pairing_arr.stds[i, :],
                        color=femcolor, capsize=2,
                        label="female " + Const.subpop_legend[i])
            ax.errorbar(self.bin_mids+0.002,
                        self.male_pairing_arr.means[i, :],
                        yerr=self.male_pairing_arr.stds[i, :],
                        color=color, capsize=2,
                        label="male "+Const.subpop_legend[i])
            ax = plot_util.setup_space_plot(ax, 2.5, "n pairings",
                                            Const.subpop_legend[i])
            ax.legend(fontsize="8")
        fig.suptitle("Mating Success")
        fig.tight_layout(pad=1.0)
        fig.show()

    def plot_pairing_heatmap(self):
        fig0, axs0 = plt.subplots(3, 3, figsize=(12, 9))
        pairing_bins = np.arange(self.n_pairing_bins + 1) - 0.5
        bins = np.arange(0, 1 + self.bin_size, self.bin_size)
        X, Y = np.meshgrid(bins, pairing_bins)
        subpop_n = np.sum(self.n_arr, axis=2)
        subpop_pairing0 = np.sum(self.female_pairing_arr.sums, axis=1)
        for i in np.arange(PedigreeLike.n_subpops):
            ax = axs0[np.unravel_index(i, (3, 3))]
            Z = self.norm_pairings[i, 0, :, :]
            Z = np.rot90(np.fliplr(Z))
            p0 = ax.pcolormesh(X, Y, Z, vmin=0, vmax=1, cmap='plasma')
            ax.set_ylim(-0.5, 4.5)
            failures = np.sum(self.pairing_hist[i, 0, :, 0])
            successrate = np.round(1 - failures / subpop_n[i, 0], 2)
            ax.set_title(f"{Const.subpop_legend[i]} "
                         f"ratio {np.round(subpop_pairing0[i] / subpop_n[i, 0], 2)}"
                         f" successrate {successrate}")
            fig0.colorbar(p0)
        fig0.suptitle("Female number of pairings")
        fig0.tight_layout(pad=1.0)
        fig0.show()

        fig1, axs1 = plt.subplots(3, 3, figsize=(12, 9))
        subpop_pairing1 = np.sum(self.male_pairing_arr.sums, axis=1)
        for i in np.arange(PedigreeLike.n_subpops):
            ax = axs1[np.unravel_index(i, (3, 3))]
            Z = self.norm_pairings[i, 1, :, :]
            Z = np.rot90(np.fliplr(Z))
            p0 = ax.pcolormesh(X, Y, Z, vmin=0, vmax=1, cmap='plasma')
            ax.set_ylim(-0.5, 4.5)
            failures = np.sum(self.pairing_hist[i, 1, :, 0])
            successrate = np.round(1 - failures / subpop_n[i, 0], 2)
            ax.set_title(f"{Const.subpop_legend[i]} "
                         f"ratio {np.round(subpop_pairing1[i] / subpop_n[i, 1], 2)}"
                         f" successrate {successrate}")
            fig1.colorbar(p0)
        fig1.suptitle("Male number of pairings")
        fig1.tight_layout(pad=1.0)
        fig1.show()

    def plot_fecundity_statistics(self):
        fig, axs = plt.subplots(3, 3, figsize=(13, 10))
        for i in np.arange(PedigreeLike.n_subpops):
            ax = axs[np.unravel_index(i, (3, 3))]
            color = colors.to_rgb(Const.subpop_colors[i])
            femcolor = [c * 0.5 for c in color]
            ax.errorbar(self.bin_mids, self.female_fecundity_arr.means[i, :],
                        yerr=self.female_fecundity_arr.stds[i, :],
                        color=femcolor, capsize=2,
                        label="female " + Const.subpop_legend[i])
            ax.errorbar(self.bin_mids+0.002,
                        self.male_fecundity_arr.means[i, :],
                        yerr=self.male_fecundity_arr.stds[i, :],
                        color=color, capsize=2,
                        label="male "+Const.subpop_legend[i])
            ax = plot_util.setup_space_plot(ax, 6, "n offspring",
                                            Const.subpop_legend[i])
            ax.legend(fontsize="8")
        fig.suptitle("Fecundity")
        fig.tight_layout(pad=1.0)
        fig.show()

    def fecundity_heatmap(self):
        fig0, axs0 = plt.subplots(3, 3, figsize=(12, 9))
        fecundity_bins = np.arange(self.n_fecundity_bins + 1) - 0.5
        bins = np.arange(0, 1 + self.bin_size, self.bin_size)
        X, Y = np.meshgrid(bins, fecundity_bins)
        subpop_n = np.sum(self.n_arr, axis=2)
        subpop_fecs = np.sum(self.female_fecundity_arr.sums, axis=1)
        for i in np.arange(PedigreeLike.n_subpops):
            ax = axs0[np.unravel_index(i, (3, 3))]
            Z = self.norm_fecundity[i, 0, :, :]
            Z = np.rot90(np.fliplr(Z))
            p0 = ax.pcolormesh(X, Y, Z, vmin=0, vmax=1, cmap='plasma')
            ax.set_ylim(-0.5, 7.5)
            ax.set_title(f"{Const.subpop_legend[i]} "
                         f"ratio {np.round(subpop_fecs[i] / subpop_n[i, 0], 2)}")
            fig0.colorbar(p0)
        fig0.suptitle("Female fecundities")
        fig0.show()


def get_bins(bin_size):
    """Helper function to get spatial bins"""
    n_bins = int(1 / bin_size)
    bin_edges = np.linspace(0, 1, n_bins + 1)
    return bin_edges, n_bins


def get_n_bins(bin_size):
    """Return the number of bins at a given bin size"""
    return int(1 / bin_size)


def get_bin_mids(bin_size):
    """Return the centers of the spatial bins specified by bin_size"""
    n_bins = get_n_bins(bin_size)
    h = bin_size / 2
    return np.linspace(h, 1 - h, n_bins)


def get_time_string():
    return str(time.strftime("%H:%M:%S", time.localtime()))