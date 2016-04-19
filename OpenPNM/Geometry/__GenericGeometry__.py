# -*- coding: utf-8 -*-
"""
===============================================================================
GenericGeometry -- Base class to manage pore scale geometry
===============================================================================

"""
import scipy as sp
from OpenPNM.Base import Core
from OpenPNM.Postprocessing import Plots
from OpenPNM.Base import logging
from OpenPNM.Network import GenericNetwork
logger = logging.getLogger(__name__)


class GenericGeometry(Core):
    r"""
    GenericGeometry - Base class to construct a Geometry object

    Parameters
    ----------
    network : OpenPNM Network Object

    pores and/or throats : array_like
        The list of pores and throats where this physics applies. If either are
        left blank this will apply the Geometry nowhere.  The locations can be
        changed after instantiation using ``set_locations()``.

    name : string
        A unique name to apply to the object.  This name will also be used as a
        label to identify where this geometry applies.

    Examples
    --------
    >>> import OpenPNM
    >>> pn = OpenPNM.Network.TestNet()
    >>> Ps = pn.pores()  # Get all pores
    >>> Ts = pn.throats()  # Get all throats
    >>> geom = OpenPNM.Geometry.GenericGeometry(network=pn,
    ...                                         pores=Ps,
    ...                                         throats=Ts)
    """

    def __init__(self, network=None, pores=[], throats=[], **kwargs):
        super().__init__(**kwargs)
        logger.name = self.name

        if network is None:
            self._net = GenericNetwork()
        else:
            self._net = network  # Attach network to self
            # Register self with network.geometries
            self._net._geometries.append(self)

        # Initialize a label dictionary in the associated network
        self._net['pore.'+self.name] = False
        self._net['throat.'+self.name] = False
        try:
            self.set_locations(pores=pores, throats=throats)
        except:
            self.controller.purge_object(self)
            raise Exception('Provided locations are in use, instantiation cancelled')

    def __getitem__(self, key):
        element = key.split('.')[0]
        # Convert self.name into 'all'
        if key.split('.')[-1] == self.name:
            key = element + '.all'

        if key in list(self.keys()):  # Look for data on self...
            return super(GenericGeometry, self).__getitem__(key)
        if key == 'throat.conns':  # Handle specifically
            [P1, P2] = \
                self._net['throat.conns'][self._net[element+'.'+self.name]].T
            Pmap = sp.zeros((self._net.Np,), dtype=int) - 1
            Pmap[self._net.pores(self.name)] = self.Ps
            conns = sp.array([Pmap[P1], Pmap[P2]]).T
            # Replace -1's with nans
            if sp.any(conns == -1):
                conns = sp.array(conns, dtype=object)
                conns[sp.where(conns == -1)] = sp.nan
            return conns
        else:  # ...Then check Network
            return self._net[key][self._net[element+'.'+self.name]]

    def set_locations(self, pores=None, throats=None, mode='add'):
        r"""
        Used for assigning Geometry objects to specified locations

        Parameters
        ----------
        pores : array_like
            The pore locations in the Network where this object is to apply

        throats : array_like
            The throat locations in the Network where this object is to apply

        mode : string
            Either 'add' (default) or 'remove' the object from the specified
            locations

        Examples
        --------
        >>> import OpenPNM
        >>> pn = OpenPNM.Network.TestNet()
        >>> pn.Np
        125
        >>> geom = OpenPNM.Geometry.GenericGeometry(network=pn,
        ...                                         pores=sp.arange(5, 125),
        ...                                         throats=pn.Ts)
        >>> [geom.Np, geom.Nt]
        [120, 300]
        >>> geom['pore.dummy'] = True
        >>> health = pn.check_geometry_health()
        >>> pores = health['undefined_pores']
        >>> geom.set_locations(pores=pores)
        >>> [geom.Np, geom.Nt]
        [125, 300]

        The label 'pore.dummy' was assigned 'before' these pores were added
        >>> geom.pores(labels='dummy', mode='not')
        array([0, 1, 2, 3, 4])
        >>> geom.set_locations(pores=pores, mode='remove')
        >>> [geom.Np, geom.Nt]
        [120, 300]

        # All pores without 'pore.dummy' label are gone
        >>> geom.num_pores(labels='dummy', mode='not')
        0
        """
        if mode == 'add':
            # Check if any constant values exist on the object
            for item in self.props():
                if (item not in self.models.keys()) or \
                   (self.models[item]['regen_mode'] == 'constant'):
                    raise Exception('Constant properties found on object, ' +
                                    'cannot increase size')
            if pores is not None:
                self._add_locations(element='pores', locations=pores)
            if throats is not None:
                self._add_locations(element='throats', locations=throats)
        if mode == 'remove':
            if pores is not None:
                self._drop_locations(element='pores', locations=pores)
            if throats is not None:
                self._drop_locations(element='throats', locations=throats)
        # Finally, regenerate models to correct the length of all arrays
        self.models.regenerate()

    def _drop_locations(self, element, locations):
        net = self._net
        element = self._parse_element(element, single=True)
        locations = self._parse_locations(locations)

        self_inds = net._map(element=element,
                             locations=locations,
                             target=self)
        keep = ~self._tomask(locations=self_inds, element=element)
        for item in list(self.keys()):
            if item.split('.')[0] == element:
                temp = self[item][keep]
                self.update({item: temp})
        # Set locations in Network dictionary
        net[element+'.'+self.name][locations] = False

    def _add_locations(self, element, locations):
        net = self._net
        element = self._parse_element(element, single=True)
        locations = self._parse_locations(locations)

        # Ensure locations are not already assigned to another Geometry
        temp = sp.zeros(net._count(element=element), dtype=int)
        geoms = net._find_object(obj_type='geometry')
        for item in geoms:
            inds = net._get_indices(element=element, labels=item)
            temp[inds] += 1
        temp[locations] += 1  # Increment proposed locations
        if sp.any(temp[locations] > 1):
            raise Exception('Some of the given '+element+' are already ' +
                            'assigned to an existing object')

        # Create new 'all' label for new size
        new_len = self._count(element=element) + sp.size(locations)
        self.update({element+'.all': sp.ones((new_len, ), dtype=bool)})

        # Set locations in Network dictionary
        inds_orig = net._get_indices(element=element, labels=self.name)
        if element+'.'+self.name not in net.keys():
            net[element+'.'+self.name] = False
        net[element+'.'+self.name][locations] = True
        inds_new = net._get_indices(element=element, labels=self.name)

        # Increase size of labels (add False at new locations)
        labels = self.labels()
        labels.remove(element+'.all')
        for item in labels:
            if item.split('.')[0] == element:
                net[element+'.'+'blank'] = False
                net[element+'.'+'blank'][inds_orig] = self[item]
                self[item] = net[element+'.'+'blank'][inds_new]
        net.pop(element+'.'+'blank', None)

    def plot_histograms(self,
                        throat_diameter='throat.diameter',
                        pore_diameter='pore.diameter',
                        throat_length='throat.length'):

        Plots.distributions(obj=self,
                            throat_diameter=throat_diameter,
                            pore_diameter=pore_diameter,
                            throat_length=throat_length)

    plot_histograms.__doc__ = Plots.distributions.__doc__
