#!/usr/bin/env python3

###############################################################################
#                                                                             #
# RMG - Reaction Mechanism Generator                                          #
#                                                                             #
# Copyright (c) 2002-2020 Prof. William H. Green (whgreen@mit.edu),           #
# Prof. Richard H. West (r.west@neu.edu) and the RMG Team (rmg_dev@mit.edu)   #
#                                                                             #
# Permission is hereby granted, free of charge, to any person obtaining a     #
# copy of this software and associated documentation files (the 'Software'),  #
# to deal in the Software without restriction, including without limitation   #
# the rights to use, copy, modify, merge, publish, distribute, sublicense,    #
# and/or sell copies of the Software, and to permit persons to whom the       #
# Software is furnished to do so, subject to the following conditions:        #
#                                                                             #
# The above copyright notice and this permission notice shall be included in  #
# all copies or substantial portions of the Software.                         #
#                                                                             #
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR  #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,    #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER      #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING     #
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER         #
# DEALINGS IN THE SOFTWARE.                                                   #
#                                                                             #
###############################################################################


"""
This module contains functions for load existing RMG simulations
by reading in files.
"""
import os.path
import warnings

from rmgpy.chemkin import load_chemkin_file
from rmgpy.solver.base import TerminationConversion
from rmgpy.solver.liquid import LiquidReactor
from rmgpy.solver.mbSampled import MBSampledReactor
from rmgpy.solver.surface import SurfaceReactor


def load_rmg_job(input_file, chemkin_file=None, species_dict=None, generate_images=True, use_java=False,
                 use_chemkin_names=False, check_duplicates=True):
    if use_java:
        # The argument is an RMG-Java input file
        warnings.warn("The RMG-Java input is no longer supported and may be" \
                      "removed in version 2.3.", DeprecationWarning)
        rmg = load_rmg_java_job(input_file, chemkin_file, species_dict, generate_images,
                                use_chemkin_names=use_chemkin_names, check_duplicates=check_duplicates)

    else:
        # The argument is an RMG-Py input file
        rmg = load_rmg_py_job(input_file, chemkin_file, species_dict, generate_images,
                              use_chemkin_names=use_chemkin_names, check_duplicates=check_duplicates)

    return rmg


def load_rmg_py_job(input_file, chemkin_file=None, species_dict=None, generate_images=True,
                    use_chemkin_names=False, check_duplicates=True):
    """
    Load the results of an RMG-Py job generated from the given `input_file`.
    """
    from rmgpy.rmg.main import RMG

    # Load the specified RMG input file
    rmg = RMG(input_file=input_file)
    rmg.load_input(input_file)
    rmg.output_directory = os.path.abspath(os.path.dirname(input_file))

    # Load the final Chemkin model generated by RMG
    if not chemkin_file:
        chemkin_file = os.path.join(os.path.dirname(input_file), 'chemkin', 'chem.inp')
    if not species_dict:
        species_dict = os.path.join(os.path.dirname(input_file), 'chemkin', 'species_dictionary.txt')
    species_list, reaction_list = load_chemkin_file(chemkin_file, species_dict,
                                                    use_chemkin_names=use_chemkin_names,
                                                    check_duplicates=check_duplicates)

    # Created "observed" versions of all reactive species that are not explicitly
    # identified as  "constant" species
    for reaction_system in rmg.reaction_systems:
        if isinstance(reaction_system, MBSampledReactor):
            observed_species_list = []
            for species in species_list:
                if '_obs' not in species.label and species.reactive:
                    for constant_species in reaction_system.constantSpeciesList:
                        if species.is_isomorphic(constant_species):
                            break
                    else:
                        for species2 in species_list:
                            if species2.label == species.label + '_obs':
                                break
                        else:
                            observedspecies = species.copy(deep=True)
                            observedspecies.label = species.label + '_obs'
                            observed_species_list.append(observedspecies)

            species_list.extend(observed_species_list)

    # Map species in input file to corresponding species in Chemkin file
    species_dict = {}
    for spec0 in rmg.initial_species:
        for species in species_list:
            if species.is_isomorphic(spec0):
                species_dict[spec0] = species
                break

    # Generate flux pairs for each reaction if needed
    for reaction in reaction_list:
        if not reaction.pairs:
            reaction.generate_pairs()

    # Replace species in input file with those in Chemkin file
    for reaction_system in rmg.reaction_systems:
        if isinstance(reaction_system, LiquidReactor):
            # If there are constant species, map their input file names to
            # corresponding species in Chemkin file
            if reaction_system.const_spc_names:
                const_species_dict = {}
                for spec0 in rmg.initial_species:
                    for constSpecLabel in reaction_system.const_spc_names:
                        if spec0.label == constSpecLabel:
                            const_species_dict[constSpecLabel] = species_dict[spec0].label
                            break
                reaction_system.const_spc_names = [const_species_dict[sname] for sname in reaction_system.const_spc_names]

            reaction_system.initial_concentrations = dict(
                [(species_dict[spec], conc) for spec, conc in reaction_system.initial_concentrations.items()])
        elif isinstance(reaction_system, SurfaceReactor):
            reaction_system.initial_gas_mole_fractions = dict(
                [(species_dict[spec], frac) for spec, frac in reaction_system.initial_gas_mole_fractions.items()])
            reaction_system.initial_surface_coverages = dict(
                [(species_dict[spec], frac) for spec, frac in reaction_system.initial_surface_coverages.items()])
        else:
            reaction_system.initial_mole_fractions = dict(
                [(species_dict[spec], frac) for spec, frac in reaction_system.initial_mole_fractions.items()])

        for t in reaction_system.termination:
            if isinstance(t, TerminationConversion):
                t.species = species_dict[t.species]
        if reaction_system.sensitive_species != ['all']:
            reaction_system.sensitive_species = [species_dict[spec] for spec in reaction_system.sensitive_species]

    # Set reaction model to match model loaded from Chemkin file
    rmg.reaction_model.core.species = species_list
    rmg.reaction_model.core.reactions = reaction_list

    # Generate species images
    if generate_images:
        species_path = os.path.join(os.path.dirname(input_file), 'species')
        try:
            os.mkdir(species_path)
        except OSError:
            pass
        for species in species_list:
            path = os.path.join(species_path, '{0!s}.png'.format(species))
            if not os.path.exists(path):
                species.molecule[0].draw(str(path))

    return rmg


def load_rmg_java_job(input_file, chemkin_file=None, species_dict=None, generate_images=True,
                      use_chemkin_names=False, check_duplicates=True):
    """
    Load the results of an RMG-Java job generated from the given `input_file`.
    """
    warnings.warn("The RMG-Java input is no longer supported and may be" \
                  "removed in version 2.3.", DeprecationWarning)
    from rmgpy.rmg.main import RMG
    from rmgpy.molecule import Molecule

    # Load the specified RMG-Java input file
    # This implementation only gets the information needed to generate flux diagrams
    rmg = RMG(input_file=input_file)
    rmg.load_rmg_java_input(input_file)
    rmg.output_directory = os.path.abspath(os.path.dirname(input_file))

    # Load the final Chemkin model generated by RMG-Java
    if not chemkin_file:
        chemkin_file = os.path.join(os.path.dirname(input_file), 'chemkin', 'chem.inp')
    if not species_dict:
        species_dict = os.path.join(os.path.dirname(input_file), 'RMG_Dictionary.txt')
    species_list, reaction_list = load_chemkin_file(chemkin_file, species_dict,
                                                    use_chemkin_names=use_chemkin_names,
                                                    check_duplicates=check_duplicates)

    # Bath gas species don't appear in RMG-Java species dictionary, so handle
    # those as a special case
    for species in species_list:
        if species.label == 'Ar':
            species.molecule = [Molecule().from_smiles('[Ar]')]
        elif species.label == 'Ne':
            species.molecule = [Molecule().from_smiles('[Ne]')]
        elif species.label == 'He':
            species.molecule = [Molecule().from_smiles('[He]')]
        elif species.label == 'N2':
            species.molecule = [Molecule().from_smiles('N#N')]

    # Map species in input file to corresponding species in Chemkin file
    species_dict = {}
    for spec0 in rmg.initial_species:
        for species in species_list:
            if species.is_isomorphic(spec0):
                species_dict[spec0] = species
                break

    # Generate flux pairs for each reaction if needed
    for reaction in reaction_list:
        if not reaction.pairs:
            reaction.generate_pairs()

    # Replace species in input file with those in Chemkin file
    for reaction_system in rmg.reaction_systems:
        reaction_system.initial_mole_fractions = dict(
            [(species_dict[spec], frac) for spec, frac in reaction_system.initial_mole_fractions.items()])
        for t in reaction_system.termination:
            if isinstance(t, TerminationConversion):
                if t.species not in list(species_dict.values()):
                    t.species = species_dict[t.species]

    # Set reaction model to match model loaded from Chemkin file
    rmg.reaction_model.core.species = species_list
    rmg.reaction_model.core.reactions = reaction_list

    # RMG-Java doesn't generate species images, so draw them ourselves now
    if generate_images:
        species_path = os.path.join(os.path.dirname(input_file), 'species')
        try:
            os.mkdir(species_path)
        except OSError:
            pass
        for species in species_list:
            path = os.path.join(species_path + '/{0!s}.png'.format(species))
            if not os.path.exists(path):
                species.molecule[0].draw(str(path))

    return rmg
