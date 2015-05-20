r"""
===============================================================================
Submodule -- throat_diameter
===============================================================================

"""
import scipy as _sp
import numpy as np

import OpenPNM.Utilities.transformations as tr
from scipy.spatial import ConvexHull
import time


def cylinder(geometry, tsd_name, tsd_shape, tsd_loc, tsd_scale,
             throat_seed='throat.seed', tsd_offset=0, **kwargs):
    r"""
    Calculate throat diameter from seeds for a cylindrical throat
    """
    import scipy.stats as spst
    prob_fn = getattr(spst, tsd_name)
    P = prob_fn(tsd_shape, loc=tsd_loc, scale=tsd_scale)
    value = P.ppf(geometry[throat_seed]) + tsd_offset
    return value


def voronoi(geometry, throat_area='throat.area', **kwargs):
    r"""
    Calculate throat diameter from analysis of Voronoi facets
    Equivalent circular diameter from voronoi area
    Could do better here and work out minimum diameter from verts
    """
    areas = geometry[throat_area]
    value = 2*_sp.sqrt(areas/_sp.pi)  # 64 bit sqrt doesn't work!
    return value


def incircle(geometry, **kwargs):
    r"""
    Calculate the incircle diameter by linear programming and the simplex search
    algorithm using the offset vertices generated by the voronoi diagram offsetting
    routine
    """
    import warnings
    try:
        import pulp as pu
        Nt = geometry.num_throats()
        verts = geometry['throat.offset_vertices']
        normals = geometry['throat.normal']
        value = _sp.zeros(Nt)
        for i in range(Nt):
            if len(verts[i]) > 2:
                pts = tr.rotate_and_chop(verts[i], normals[i], [0, 0, 1])
                # Work out central point to use as initial guess
                C = np.mean(pts, axis=0)
                # Compute convex hull to find points lying on the hull in order
                hull = ConvexHull(pts, qhull_options='QJ Pp')
                # For each simplex making up the hull collect the end points
                A = pts[hull.vertices]
                B = pts[np.roll(hull.vertices, -1)]
                I = np.array([[0, 1], [-1, 0]])
                # Normal of the simplices
                N = np.dot((B-A), I)
                # Normalize the normal vector
                L = np.linalg.norm(N, axis=1)
                F = np.vstack((L, L)).T
                N /= F
                # Mid-points of the simplex
                M = (B+A)/2
                # If normals point out of hull change sign to point in
                pointing_out = (np.sum((M-C)*N, axis=1) > 0)
                N[pointing_out] *= -1
                # Define Linear Program Variables
                # The centre of the incircle adjustment
                cx = pu.LpVariable('cx', None, None, pu.LpContinuous)
                cy = pu.LpVariable('cy', None, None, pu.LpContinuous)
                # Radius of the incircle
                R = pu.LpVariable('R', 0, None, pu.LpContinuous)
                # Slack variables for shortest distance between centre and simplices
                S = pu.LpVariable.dict('SlackVariable', range(len(A)), 0,
                                       None, pu.LpContinuous)
                # Set up LP problem
                prob = pu.LpProblem('FindInRadius', pu.LpMaximize)
                # Objective Function
                prob += R
                for j in range(len(A)):
                    # Ni.(C-Ai)-Si = 0
                    prob += N[j][0]*(C[0]+cx) + N[j][1]*(C[1]+cy) - \
                        N[j][0]*A[j][0] - N[j][1]*A[j][1] - S[j] == 0
                    # Si >= R
                    prob += S[j] >= R
                # Solve the LP
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    prob.solve()
                # As the radius is the objective function we can get it from the
                # objective or as R.value()
                value[i] = 2*R.value()
            else:
                value[i] = 0.0

        return value
    except ImportError:
        print('Cannot use incircle method without installing pulp package')


def minpore(network,
            geometry,
            **kwargs):

    r"""
    Assign the throat diameter to be equal to the smallest connecting pore diameter
    If zero (in case of boundaries) take it to be the maximum of the connecting pore diameters
    """
    gTs = geometry.throats()
    nTs = geometry.map_throats(network, gTs)
    pDs = network["pore.diameter"][network["throat.conns"][nTs]]
    value = np.min(pDs, axis=1)
    value[value == 0.0]=np.max(pDs, axis=1)[value == 0.0]
    return value