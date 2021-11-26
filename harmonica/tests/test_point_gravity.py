# Copyright (c) 2018 The Harmonica Developers.
# Distributed under the terms of the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause
#
# This code is part of the Fatiando a Terra project (https://www.fatiando.org)
#
"""
Test forward modelling for point masses.
"""
import os
from pathlib import Path
import warnings
import numpy as np
import numpy.testing as npt
import pytest
import verde as vd

from ..constants import GRAVITATIONAL_CONST
from ..forward.point import point_gravity, point_mass_gravity
from ..forward.utils import distance_cartesian

from .utils import run_only_with_numba

MODULE_DIR = Path(os.path.dirname(__file__))
TEST_DATA_DIR = MODULE_DIR / "data"


def test_invalid_coordinate_system():
    "Check if invalid coordinate system is passed"
    coordinates = [0.0, 0.0, 0.0]
    point_mass = [0.0, 0.0, 0.0]
    mass = 1.0
    with pytest.raises(ValueError):
        point_gravity(
            coordinates,
            point_mass,
            mass,
            "potential",
            "this-is-not-a-valid-coordinate-system",
        )


def test_not_implemented_field():
    """
    Check if NotImplementedError is raised after asking a non-implemented field
    """
    coordinates = [0.0, 0.0, 0.0]
    point_mass = [0.0, 0.0, 0.0]
    mass = 1.0
    coordinate_system = "spherical"
    for field in ("g_northing", "g_easting"):
        with pytest.raises(NotImplementedError):
            point_gravity(
                coordinates,
                point_mass,
                mass,
                field,
                coordinate_system,
            )


def test_invalid_field():
    "Check if an invalid gravitational field is passed as argument"
    coordinates = [0.0, 0.0, 0.0]
    point_mass = [0.0, 0.0, 0.0]
    mass = 1.0
    for coordinate_system in ("spherical", "cartesian"):
        with pytest.raises(ValueError):
            point_gravity(
                coordinates,
                point_mass,
                mass,
                "this-field-does-not-exist",
                coordinate_system,
            )


def test_invalid_masses_array():
    "Check if error is raised when masses shape does not match points shape"
    # Create a set of 3 point masses
    points = [[-10, 0, 10], [-10, 0, 10], [-100, 0, 100]]
    # Generate a two element masses
    masses = [1000, 2000]
    coordinates = [0, 0, 250]
    with pytest.raises(ValueError):
        point_gravity(
            coordinates,
            points,
            masses,
            field="potential",
            coordinate_system="cartesian",
        )


# ---------------------------
# Cartesian coordinates tests
# ---------------------------


@pytest.fixture(name="point_mass")
def fixture_point_mass():
    """
    Defines a point located in the origin with a mass of 500kg
    """
    point = [0, 0, 0]
    mass = [5000]
    return point, mass


@pytest.fixture(name="sample_coordinates_potential")
def fixture_sample_coordinates_potential():
    """
    Define a sample computation points and the gravity potential field
    generated by the point_mass.
    """
    sample_data_file = TEST_DATA_DIR / "sample_point_gravity.csv"
    easting, northing, upward, potential = np.loadtxt(
        sample_data_file, delimiter=",", unpack=True
    )
    return (easting, northing, upward, potential)


@pytest.mark.use_numba
def test_potential_cartesian_known_values(point_mass, sample_coordinates_potential):
    """
    Compare the computed gravitational potential with reference values
    """
    point, mass = point_mass[:]
    coordinates = sample_coordinates_potential[:3]
    precomputed_potential = sample_coordinates_potential[-1]
    # Compute potential gravity field on each computation point
    results = point_gravity(coordinates, point, mass, "potential", "cartesian")
    npt.assert_allclose(results, precomputed_potential)


@pytest.mark.use_numba
def test_point_mass_gravity_deprecated(point_mass, sample_coordinates_potential):
    """
    Test the soon-to-be-deprecated point_mass_gravity function
    """
    point, mass = point_mass[:]
    coordinates = sample_coordinates_potential[:3]
    precomputed_potential = sample_coordinates_potential[-1]
    # Check if a FutureWarning is raised
    with warnings.catch_warnings(record=True) as warn:
        results = point_mass_gravity(coordinates, point, mass, "potential", "cartesian")
        assert len(warn) == 1
        assert issubclass(warn[-1].category, FutureWarning)
    npt.assert_allclose(results, precomputed_potential)


@pytest.mark.use_numba
def test_potential_symmetry_cartesian():
    """
    Test if potential field of a point mass has symmetry in Cartesian coords
    """
    # Define a single point mass
    point_mass = [1.1, 1.2, 1.3]
    masses = [2670]
    # Define a set of computation points at a fixed distance from the point
    # mass
    distance = 3.3
    easting = point_mass[0] * np.ones(6)
    northing = point_mass[1] * np.ones(6)
    upward = point_mass[2] * np.ones(6)
    easting[0] += distance
    easting[1] -= distance
    northing[2] += distance
    northing[3] -= distance
    upward[4] += distance
    upward[5] -= distance
    coordinates = [easting, northing, upward]
    # Compute potential gravity field on each computation point
    results = point_gravity(coordinates, point_mass, masses, "potential", "cartesian")
    npt.assert_allclose(*results)


@pytest.mark.use_numba
@pytest.mark.parametrize("field", ("g_northing", "g_easting", "g_z"))
def test_acceleration_symmetry_cartesian(field):
    """
    Test if the acceleration components verify the expected symmetry

    Use Cartesian coordinates
    """
    # Define a single point mass
    point_mass = [1.1, 1.2, 1.3]
    masses = [2670]
    # Define a pair of computation points at each side of the point mass along
    # the direction given by the field parameter
    distance = 3.3
    easting = point_mass[0] * np.ones(2)
    northing = point_mass[1] * np.ones(2)
    upward = point_mass[2] * np.ones(2)
    if field == "g_northing":
        northing[0] += distance
        northing[1] -= distance
    elif field == "g_easting":
        easting[0] += distance
        easting[1] -= distance
    elif field == "g_z":
        upward[0] += distance
        upward[1] -= distance
    coordinates = [easting, northing, upward]
    # Compute gravity acceleration component on each computation point
    results = point_gravity(coordinates, point_mass, masses, field, "cartesian")
    npt.assert_allclose(results[0], -results[1])


def acceleration_finite_differences(coordinates, point, mass, field, delta=0.05):
    """
    Compute acceleration components through finite differences

    Parameters
    ----------
    coordinates : tuple
        The coordinates of the computation point where the approximated
        acceleration components will be computed.
    point : tuple
        The coordinates of the point source.
    mass : float
        Mass of the point source.
    field : str
        Acceleration component that needs to be approximated ("g_easting",
        "g_northing", "g_z").
    delta : float
        Distance use to compute the finite difference in meters.

    Returns
    -------
    finite_diff : float
        Approximation of the acceleration component.
    error : float
        Relative error of the approximation (unitless).
    """
    # Build a two computation points slightly shifted from the original
    # computation point by a small delta
    coordinates_pair = tuple([coord, coord] for coord in coordinates)
    if field == "g_easting":
        index = 0
    elif field == "g_northing":
        index = 1
    elif field == "g_z":
        index = 2
    coordinates_pair[index][0] -= delta
    coordinates_pair[index][1] += delta
    # Compute the potential on both points
    potential = point_gravity(
        coordinates_pair, point, mass, field="potential", coordinate_system="cartesian"
    )
    # Compute the difference between the two values
    finite_diff = (potential[1] - potential[0]) / (2 * delta)
    # Convert to mGal
    finite_diff *= 1e5
    # Remember that the ``g_z`` field returns the downward component of the
    # gravitational acceleration. As a consequence, the numerical
    # derivative dive is multiplied by -1.
    if field == "g_z":
        finite_diff *= -1
    # Compute the bounding error of the approximation
    distance = distance_cartesian(coordinates, point)
    relative_error = 3 / 2 * (delta / distance) ** 2
    return finite_diff, relative_error


@pytest.mark.use_numba
@pytest.mark.parametrize("field", ("g_northing", "g_easting", "g_z"))
@pytest.mark.parametrize(
    "coordinates, point, mass",
    (
        [(0, -39, -13), (1, -67, -300.7), 250],
        [(-3, 24, -10), (20, 54, -500.7), 200],
    ),
    ids=["set1", "set2"],
)
def test_acceleration_finite_diff_cartesian(coordinates, point, mass, field):
    """
    Test acceleration components against a finite difference of the potential
    """
    # Compute the z component
    result = point_gravity(coordinates, point, mass, field, "cartesian")
    # Compute the derivative of potential through finite differences
    finite_diff, relative_error = acceleration_finite_differences(
        coordinates, point, mass, field
    )
    # Compare the results
    npt.assert_allclose(result, finite_diff, rtol=relative_error)


@pytest.mark.use_numba
@pytest.mark.parametrize("field", ("g_northing", "g_easting", "g_z"))
def test_acceleration_sign(field):
    """
    Test if acceleration components have the correct sign
    """
    # Define a single point mass
    point_mass = [-10, 100.2, -300.7]
    mass = [2670]
    # Define computation points
    coordinates = [np.zeros(3) for i in range(3)]
    if field == "g_easting":
        coordinates[0] = np.array([-150.7, -10, 79])
    elif field == "g_northing":
        coordinates[1] = np.array([0, 100.2, 210.7])
    elif field == "g_z":
        coordinates[2] = np.array([100.11, -300.7, -400])
    # Compute acceleration component
    results = point_gravity(coordinates, point_mass, mass, field, "cartesian")
    # Check if the sign of the results is right
    assert np.sign(mass) == np.sign(results[0])
    npt.assert_allclose(results[1], 0)
    assert np.sign(mass) == -np.sign(results[2])


@run_only_with_numba
@pytest.mark.parametrize(
    "field",
    # fmt: off
    (
        "potential", "g_z", "g_northing", "g_easting",
        "g_ee", "g_nn", "g_zz", "g_en", "g_ez", "g_nz"
    ),
    # fmt: on
)
def test_point_mass_cartesian_parallel(field):
    """
    Check if parallel and serial runs return the same result
    """
    region = (2e3, 10e3, -3e3, 5e3)
    points = vd.scatter_points(region, size=30, extra_coords=-1e3, random_state=0)
    masses = np.arange(points[0].size)
    coordinates = vd.grid_coordinates(region=region, spacing=1e3, extra_coords=0)
    result_serial = point_gravity(
        coordinates, points, masses, field=field, parallel=False
    )
    result_parallel = point_gravity(
        coordinates, points, masses, field=field, parallel=True
    )
    npt.assert_allclose(result_serial, result_parallel)


@pytest.mark.use_numba
def test_laplace_equation_cartesian():
    """
    Check if the diagonal components of the tensor satisfy Laplace equation

    Use Cartesian coordinates.
    """
    region = (2e3, 10e3, -3e3, 5e3)
    points = vd.scatter_points(region, size=30, extra_coords=-1e3, random_state=0)
    masses = np.arange(points[0].size)
    coordinates = vd.grid_coordinates(region=region, spacing=1e3, extra_coords=0)
    g_ee = point_gravity(coordinates, points, masses, field="g_ee")
    g_nn = point_gravity(coordinates, points, masses, field="g_nn")
    g_zz = point_gravity(coordinates, points, masses, field="g_zz")
    # Check if the Laplacian of the gravitational field is close to zero
    npt.assert_allclose(g_ee + g_nn, -g_zz)


class TestTensorSymmetryCartesian:

    # Define sample point source and its mass
    point = [1.1, 1.2, 1.3]
    mass = [2670]

    # Define tensor components tuple
    diagonal_fields = ["g_ee", "g_nn", "g_zz"]
    nondiagonal_fields = ["g_en", "g_ez", "g_nz"]
    tensor_fields = diagonal_fields + nondiagonal_fields

    def mirrored_computation_points(self, direction):
        """
        Create mirrored computation points to the point source

        The mirrored computation points will be mirror images along one of the
        planes given by the tensor component.

                |
           *    |    *     m: point source of mass m
                |          *: each one of the mirrored computation points
                |
        --------m--------
                |
                |
                |
                |

        Parameters
        ----------
        direction : str
            Direction along which the computation points will be mirrored.
            For example: ``"n"``

        Returns
        -------
        coordinates : tuple
            Tuple containing the coordinates of the mirrored computation points
            in the following order: easting, northing, upward.
        """
        distance = 3.3
        easting = self.point[0] * np.ones(2)
        northing = self.point[1] * np.ones(2)
        upward = self.point[2] * np.ones(2)
        if direction == "n":
            northing[0] += distance
            northing[1] -= distance
        elif direction == "e":
            easting[0] += distance
            easting[1] -= distance
        elif direction == "z":
            upward[0] += distance
            upward[1] -= distance
        return (easting, northing, upward)

    def opposite_computation_points(self, directions):
        """
        Create opposite computation points to the point source

        The opposite computation points will live in the diagonal given by the
        direction of the tensor component and be equidistant to the point
        source.
        For example:
          - if ``directions=("e", "n")``, the two computation points will be
            along the easting-northing diagonal, equidistant to the point mass.
          - if ``directions=("n", "z")``, the two computation points will be
            along the northing-upward diagonal, equidistant to the point mass.

                |
                |    *     m: point source of mass m
                |          *: each one of the opposite computation points
                |
        --------m--------
                |
                |
           *    |
                |

        Parameters
        ----------
        directions : tuple
            Tuple with the directions along which the opposition will be
            carried out. For example: ``("n", "z")``

        Returns
        -------
        coordinates : tuple
            Tuple containing the coordinates of the opposite computation points
            in the following order: easting, northing, upward.
        """
        distance = 3.3
        easting = self.point[0] * np.ones(2)
        northing = self.point[1] * np.ones(2)
        upward = self.point[2] * np.ones(2)
        if "n" in directions:
            northing[0] += distance
            northing[1] -= distance
        if "e" in directions:
            easting[0] += distance
            easting[1] -= distance
        if "z" in directions:
            upward[0] += distance
            upward[1] -= distance
        return (easting, northing, upward)

    @pytest.mark.use_numba
    @pytest.mark.parametrize("field", tensor_fields)
    def test_opposite(self, field):
        """
        Test tensor components symmetry on opposite computation points

        The values of each tensor component should be the same on opposite
        points.
        """
        # Define opposite computation points
        directions = (field[-2], field[-1])
        coordinates = self.opposite_computation_points(directions)
        # Compute gravity tensor component on each computation point
        results = point_gravity(coordinates, self.point, self.mass, field, "cartesian")
        # Check for expected symmetry
        npt.assert_allclose(results[0], results[1])

    @pytest.mark.use_numba
    @pytest.mark.parametrize("field", diagonal_fields)
    def test_mirrored_diagonals(self, field):
        """
        Test diagonal tensor components symmetry on mirrored computation points

        For diagonal tensor components, their values should be the same on
        mirrored computation points.
        """
        # Choose the direction corresponding to the diagonal tensor component
        direction = field[-1]
        # Define mirrored computation points
        coordinates = self.mirrored_computation_points(direction)
        # Compute gravity tensor component on each computation point
        results = point_gravity(coordinates, self.point, self.mass, field, "cartesian")
        # Check for expected symmetry
        npt.assert_allclose(results[0], results[1])

    @pytest.mark.use_numba
    @pytest.mark.parametrize("field", nondiagonal_fields)
    @pytest.mark.parametrize("mirror_plane", (0, 1))
    def test_mirrored_nondiagonals(self, field, mirror_plane):
        """
        Test nondiagonal tensor components symmetry on mirrored points

        For non-diagonal tensor components, their values should be opposite on
        mirrored computation points.
        """
        # Choose one of the directions of the tensor component to mirror the
        # computation points
        directions = (field[-2], field[-1])
        direction = directions[mirror_plane]
        # Define mirrored computation points
        coordinates = self.mirrored_computation_points(direction)
        # Compute gravity tensor component on each computation point
        results = point_gravity(coordinates, self.point, self.mass, field, "cartesian")
        # Check for expected symmetry
        npt.assert_allclose(results[0], -results[1])


def tensor_finite_differences(coordinates, point, mass, field, delta=0.05):
    """
    Compute tensor components through finite differences

    Parameters
    ----------
    coordinates : tuple
        The coordinates of the computation point where the approximated
        tensor components will be computed.
    point : tuple
        The coordinates of the point source.
    mass : float
        Mass of the point source.
    field : str
        Tensor component that needs to be approximated ("g_ee",
        "g_nn", "g_zz", "g_en", "g_ez", "g_nz").
    delta : float
        Distance use to compute the finite difference in meters.

    Returns
    -------
    finite_diff : float
        Approximation of the tensor component.
    error : float
        Relative error of the approximation (unitless).
    """
    # Determine the direction along which the finite difference will be
    # computed
    direction_i, direction_j = field[-2], field[-1]
    if direction_i == "e":
        direction_i = "easting"
    if direction_i == "n":
        direction_i = "northing"
    if direction_j == "e":
        direction_j = "easting"
    if direction_j == "n":
        direction_j = "northing"
    # Build a two computation points slightly shifted from the original
    # computation point by a small delta
    coordinates_pair = tuple([coord, coord] for coord in coordinates)
    if direction_j == "easting":
        index = 0
    elif direction_j == "northing":
        index = 1
    elif direction_j == "z":
        index = 2
    coordinates_pair[index][0] -= delta
    coordinates_pair[index][1] += delta
    # Compute the acceleration on both points
    acceleration = point_gravity(
        coordinates_pair,
        point,
        mass,
        field=f"g_{direction_i}",
        coordinate_system="cartesian",
    )
    # Compute the difference between the two values
    finite_diff = (acceleration[1] - acceleration[0]) / (2 * delta)
    # Convert to Eotvos
    finite_diff *= 1e-5  # convert back from mGal to SI
    finite_diff *= 1e9  # convert to Eotvos
    # The z axis points downwards, so the finite_diff should be multiplied by
    # -1
    if direction_i == "z" or direction_j == "z":
        finite_diff *= -1
    # Compute the bounding error of the approximation
    distance = distance_cartesian(coordinates, point)
    relative_error = 6 * (delta / distance) ** 2
    return finite_diff, relative_error


@pytest.mark.use_numba
@pytest.mark.parametrize("field", ("g_ee", "g_nn", "g_zz", "g_en", "g_ez", "g_nz"))
@pytest.mark.parametrize(
    "coordinates, point, mass",
    (
        [(0, -39, -13), (1, -67, -300.7), 250],
        [(-3, 24, -10), (20, 54, -500.7), 200],
    ),
    ids=["set1", "set2"],
)
def test_tensor_finite_diff_cartesian(coordinates, point, mass, field):
    """
    Test tensor components against a finite difference of the acceleration
    """
    # Compute the z component
    result = point_gravity(coordinates, point, mass, field, "cartesian")
    # Compute the derivative of potential through finite differences
    finite_diff, relative_error = tensor_finite_differences(
        coordinates, point, mass, field
    )
    # Compare the results
    npt.assert_allclose(result, finite_diff, rtol=relative_error)


# ---------------------------
# Spherical coordinates tests
# ---------------------------
@pytest.mark.use_numba
def test_point_mass_on_origin():
    "Check potential and g_z of point mass on origin in spherical coordinates"
    point_mass = [0.0, 0.0, 0.0]
    mass = 2.0
    radius = np.logspace(1, 8, 5)
    longitude = np.linspace(-180, 180, 37)
    latitude = np.linspace(-90, 90, 19)
    longitude, latitude, radius = np.meshgrid(longitude, latitude, radius)
    # Analytical solutions (accelerations are in mgal and tensor components in
    # eotvos)
    analytical = {
        "potential": GRAVITATIONAL_CONST * mass / radius,
        "g_z": GRAVITATIONAL_CONST * mass / radius ** 2 * 1e5,
    }
    # Compare results with analytical solutions
    for field, solution in analytical.items():
        npt.assert_allclose(
            point_gravity(
                [longitude, latitude, radius], point_mass, mass, field, "spherical"
            ),
            solution,
        )


@pytest.mark.use_numba
@pytest.mark.parametrize("field", ("potential", "g_z"))
def test_point_mass_same_radial_direction(field):
    """
    Check potential and g_z of point mass and computation point on same radius
    """
    sphere_radius = 3.0
    mass = 2.0
    for longitude in np.linspace(-180, 180, 37):
        for latitude in np.linspace(-90, 90, 19):
            for height in np.logspace(0, 4, 5):
                point_mass = [longitude, latitude, sphere_radius]
                coordinates = [
                    np.array(longitude),
                    np.array(latitude),
                    np.array(height + sphere_radius),
                ]
                # Analytical solutions
                # (accelerations are in mgal and tensor components in eotvos)
                analytical = {
                    "potential": GRAVITATIONAL_CONST * mass / height,
                    "g_z": GRAVITATIONAL_CONST * mass / height ** 2 * 1e5,
                }
                # Compare results with analytical solutions
                npt.assert_allclose(
                    point_gravity(coordinates, point_mass, mass, field, "spherical"),
                    analytical[field],
                )


@pytest.mark.use_numba
def test_point_mass_potential_on_equator():
    "Check potential field on equator and same radial coordinate"
    radius = 3.0
    mass = 2.0
    latitude = 0.0
    for longitude_p in np.linspace(0, 350, 36):
        point_mass = [longitude_p, latitude, radius]
        for longitude in np.linspace(0, 350, 36):
            if longitude != longitude_p:
                coordinates = [
                    np.array(longitude),
                    np.array(latitude),
                    np.array(radius),
                ]
                # Analytical solutions
                # (accelerations are in mgal and tensor components in eotvos)
                distance = (
                    2 * radius * np.sin(0.5 * np.radians(abs(longitude - longitude_p)))
                )
                analytical = {"potential": GRAVITATIONAL_CONST * mass / distance}
                # Compare results with analytical solutions
                npt.assert_allclose(
                    point_gravity(
                        coordinates, point_mass, mass, "potential", "spherical"
                    ),
                    analytical["potential"],
                )


@pytest.mark.use_numba
def test_point_mass_potential_on_same_meridian():
    "Check potential field on same meridian and radial coordinate"
    radius = 3.0
    mass = 2.0
    longitude = 0.0
    for latitude_p in np.linspace(-90, 90, 19):
        point_mass = [longitude, latitude_p, radius]
        for latitude in np.linspace(-90, 90, 19):
            if latitude != latitude_p:
                coordinates = [
                    np.array(longitude),
                    np.array(latitude),
                    np.array(radius),
                ]
                # Analytical solutions
                # (accelerations are in mgal and tensor components in eotvos)
                distance = (
                    2 * radius * np.sin(0.5 * np.radians(abs(latitude - latitude_p)))
                )
                analytical = {"potential": GRAVITATIONAL_CONST * mass / distance}
                # Compare results with analytical solutions
                npt.assert_allclose(
                    point_gravity(
                        coordinates, point_mass, mass, "potential", "spherical"
                    ),
                    analytical["potential"],
                )


@run_only_with_numba
def test_point_mass_spherical_parallel():
    """
    Check if parallel and serial runs return the same result
    """
    region = (2, 10, -3, 5)
    radius = 6400e3
    points = vd.scatter_points(
        region, size=30, extra_coords=radius - 10e3, random_state=0
    )
    masses = np.arange(points[0].size)
    coordinates = vd.grid_coordinates(region=region, spacing=1, extra_coords=radius)
    for field in ("potential", "g_z"):
        result_serial = point_gravity(
            coordinates,
            points,
            masses,
            field=field,
            coordinate_system="spherical",
            parallel=False,
        )
        result_parallel = point_gravity(
            coordinates,
            points,
            masses,
            field=field,
            coordinate_system="spherical",
            parallel=True,
        )
        npt.assert_allclose(result_serial, result_parallel)
