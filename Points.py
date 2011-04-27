"""Point and Pointset enhanced array classes.

(Objects of both classes are mutable.)

    Robert Clewley, February 2006
"""

# ----------------------------------------------------------------------------

from __future__ import division

## PyDSTool imports
from utils import *
from common import *
from errors import *
from parseUtils import symbolMapClass, mapNames

## Other imports
from numpy import Inf, NaN, isfinite, array2string, r_, c_, \
    less, greater, linalg, shape, array, argsort, savetxt, \
    take, zeros, transpose, resize, indices, concatenate, rank

from numpy import complex, complexfloating, int, integer, \
     float, floating, float64, complex128, int32
from numpy import any, all, alltrue, sometrue, ndarray


import sys
from copy import copy, deepcopy


__all__ = ['Point', 'Pointset', 'isparameterized', 'pointsToPointset',
           'PointInfo', 'makeNonParameterized', 'arrayToPointset',
           'VarCaller', 'comparePointCoords', 'importPointset',
           'exportPointset', 'padPointset']

#----------------------------------------------------------------------------


class VarCaller(object):
    """Wrapper for Variable type to call Pointset and return array type."""

    def __init__(self, pts):
        if isinstance(pts, (Point, Pointset)):
            self.pts = pts
        else:
            raise TypeError("Invalid type for pts argument")

    def __call__(self, x):
        return self.pts(x).toarray()


#----------------------------------------------------------------------------


# for internal use
point_keys = ['coorddict', 'coordarray', 'coordtype', 'norm', 'labels']


class Point(object):
    """N-dimensional point class."""

    # Contains an ordered list of names for the coordinates (to
    # suggest how the points belong to a particular space specified
    # using a particular basis)
    def __init__(self, kwd=None, **kw):
        if kwd is not None:
            if kw != {}:
                raise ValueError("Cannot mix keyword dictionary and keywords")
            kw = kwd
        self._parameterized = False
        self.labels = {}
        if intersect(kw.keys(), point_keys) == []:
            # creating Point from dictionary
            temp_kw = {}
            temp_kw['coorddict'] = copy(kw)
            kw = copy(temp_kw)
        if 'coorddict' in kw:
            coorddict = {}
            try:
                ct = kw['coordtype']
            except KeyError:
                self.coordtype = float
            else:
                try:
                    self.coordtype = _num_equivtype[ct]
                except KeyError:
                    raise TypeError('Coordinate type %s not valid for Point'%str(ct))
            for c, v in kw['coorddict'].iteritems():
                if not isinstance(c, str):
                    c_key = repr(c)
                else:
                    c_key = c
                if isinstance(v, list):
                    coorddict[c_key] = array(v, self.coordtype)
                elif isinstance(v, ndarray):
                    if len(v) == 1:
                        coorddict[c_key] = v[0]
                    else:
                        coorddict[c_key] = array(v)
                    assert compareNumTypes(self.coordtype, coorddict[c_key].dtype.type), \
                           'type mismatch'
                elif isinstance(v, _float_types):
                    assert compareNumTypes(self.coordtype, _float_types), \
                           'type mismatch'
                    coorddict[c_key] = array([v], self.coordtype)
                elif isinstance(v, _int_types):
                    assert compareNumTypes(self.coordtype, _real_types), \
                           'type mismatch'
                    coorddict[c_key] = array([v], self.coordtype)
##                elif isinstance(v, _complex_types):
##                    assert compareNumTypes(self.coordtype, complex), 'type mismatch'
##                    coorddict[c_key] = array([v], self.coordtype)
                else:
                    raise TypeError("Must pass numeric type or sequence of "
                                    "numeric types")
            self.coordnames = coorddict.keys()
            # only way to order dictionary keys for array is to sort
            self.coordnames.sort()
            self.dimension = len(self.coordnames)
            datalist = []
            for c in self.coordnames:
                assert not isinstance(coorddict[c], (list, tuple)), 'type mismatch'
                datalist.append(coorddict[c][0])
            self.coordarray = array(datalist, self.coordtype)
            r = rank(self.coordarray)
            if r == 1:
                pass
            elif r == 0:
                self.coordarray = self.coordarray.ravel()
            else:
                raise ValueError("Invalid rank for coordinate array: %i"%r)
            assert self.dimension == self.coordarray.shape[0], "Invalid coord array"
        elif 'coordarray' in kw:
            # 'coordtype' key is optional unless 'array' is actually a list,
            # when this key specifies the internal Python to use
            if isinstance(kw['coordarray'], ndarray):
                # use 'array' constructor to ensure that copy is made of array
                # in case either original or new array is independently changed.
                array_temp = array(kw['coordarray'])
                try:
                    self.coordtype = _num_equivtype[array_temp.dtype.type]
                except KeyError:
                    raise TypeError('Coordinate type %s not valid for Point'%str(ct))
            elif isinstance(kw['coordarray'], list):
                try:
                    self.coordtype = _num_equivtype[kw['coordtype']]
                except KeyError:
                    raise TypeError('Coordinate type %s not valid for Point'%str(ct))
                array_temp = array(kw['coordarray'], self.coordtype)
            else:
                raise TypeError('Coordinate type %s not valid for Point'%str(type(kw['coordarray'])))
            r = rank(array_temp)
            if r == 1:
                self.coordarray = array_temp
            elif r == 0:
                self.coordarray = array_temp.ravel()
            else:
                raise ValueError("Invalid rank for coordinate array: %i"%r)
            self.dimension = self.coordarray.shape[0]
            if 'coordnames' in kw:
                if isinstance(kw['coordnames'], str):
                    coordnames = [kw['coordnames']]
                else:
                    coordnames = kw['coordnames']
            else:
                coordnames = [str(cix) for cix in range(self.dimension)]
            if len(coordnames) != self.dimension:
                print "Point initialization error:"
                print "Found coord names: ", coordnames, \
                             "(dimension = %s)"%len(coordnames)
                print "vs. data dimension =", self.dimension
                raise ValueError("Mismatch between number of coordnames and "
                                 "dimension of data")
            cs = array(coordnames)
            order = cs.argsort()
            self.coordnames = cs[order].tolist()
            self.coordarray = self.coordarray[order]
        else:
            raise ValueError("Missing coord info in keywords")
        assert isUniqueSeq(self.coordnames), 'Coordinate names must be unique'
        self.makeIxMaps()
        if 'norm' in kw:
            if kw['norm'] == 0:
                raise ValueError("Norm order for point cannot be zero")
            self._normord = kw['norm']
        else:
            self._normord = 2
        # extra information (for special bifurcation point data)
        if 'labels' in kw:
            self.addlabel(kw['labels'])


    def mapNames(self, themap):
        """Map coordinate names and label(s), using a symbol
        map of class symbolMapClass."""
        new_coordnames = array(themap(self.coordnames))
        assert isUniqueSeq(new_coordnames.tolist()), 'Coordinate names must be unique'
        order = argsort(new_coordnames)
        self.coordarray = self.coordarray[order]
        self.coordnames = new_coordnames[order].tolist()
        self.makeIxMaps()
        # the following call will be inherited by Pointset, and
        # works on Point labels-as-dict and Pointset labels-as-
        # PointInfo objects, as the latter have their own
        # mapNames method which will get called.
        self.labels = mapNames(themap, self.labels)


    def addlabel(self, label):
        if label is None:
            pass
        elif isinstance(label, str):
            self.labels = {label: {}}
        elif isinstance(label, tuple) and len(label)==2:
            if isinstance(label[0], str) and isinstance(label[1], dict):
                self.labels[label[0]] = label[1]
        elif isinstance(label, dict):
            self.labels = label
        else:
            raise TypeError("Point label must be a string, a pair, or a dict")


    def removelabel(self):
        self.labels = {}


    def makeIxMaps(self):
        self._name_ix_map = dict(zip(self.coordnames, range(self.dimension)))
        self._ix_name_map = copy(self.coordnames)


    def todict(self, aslist=False):
        """Convert Point to a dictionary of array values (or of list with aslist=True)."""
        if aslist:
            return dict(zip(self._ix_name_map, self.coordarray.tolist()))
        else:
            return dict(zip(self._ix_name_map, self.coordarray))

    def __contains__(self, coord):
        return coord in self.coordnames

    def __delitem__(self, k):
        raise NotImplementedError

    def get(self, coord, d=None):
        if coord in self.coordnames:
            return self.__call__(coord)
        else:
            return d

    def update(self, d):
        for k, v in d.iteritems():
            self.coordarray[self._map_names_to_ixs(k)] = v

    def items(self):
        return zip(self._ix_name_map, self.coordarray)

    def iteritems(self):
        return iter(zip(self._ix_name_map, self.coordarray))

    def values(self):
        return self.coordarray.tolist()

    def itervalues(self):
        return iter(self.coordarray.tolist())

    def keys(self):
        return self._ix_name_map

    def iterkeys(self):
        return iter(self._ix_name_map)

    def has_key(self, k):
        return k in self.coordnames


    def _map_names_to_ixs(self, namelist):
        try:
            try:
                # single string
                return self._name_ix_map[namelist]
            except TypeError:
                # list of strings
                return [self._name_ix_map[n] for n in namelist]
        except KeyError, e:
            raise PyDSTool_KeyError("Name not found: "+str(e))


    def __len__(self):
        return self.dimension


    def _force_coords_to_ixlist(self, x):
        if x is None:
            return range(self.dimension)
        elif x in xrange(self.dimension):
            # only used for recursive calls
            return [x]
        elif x in self.coordnames:
            # only used for recursive calls
            return [self._name_ix_map[x]]
        elif isinstance(x, _seq_types):
            if len(x) == 0:
                return range(self.dimension)
            else:
                return [self._force_coords_to_ixlist(el)[0] for el in x]
        elif isinstance(x, slice):
            stop = x.stop or self.dimension
            s1, s2, s3 = x.indices(stop)
            if s1 < 0 or s2 > self.dimension or s1 >= self.dimension:
                raise ValueError("Slice index out of range")
            return range(s1, s2, s3)
        else:
            raise ValueError("Invalid coordinate / index: %s"%str(x) + \
                             " -- coord names are: %s"%str(self.coordnames))


    def __call__(self, coords):
        if coords in xrange(self.dimension+1):
            if coords == self.dimension:
                # trap for when Point is used as an iterator, i.e. as
                # for x in pt -- avoids writing an __iter__ method that
                # will be inherited by Pointset, which already iterates fine
                raise StopIteration
            else:
                return self.coordarray[coords]
        elif coords in self.coordnames:
            ix = self._name_ix_map[coords]
            return self.coordarray[ix]
        else:
            ixlist = self._force_coords_to_ixlist(coords)
            return Point({'coordarray': self.coordarray[ixlist],
                      'coordnames': [self.coordnames[i] for i in ixlist],
                      'coordtype': self.coordtype,
                      'norm': self._normord,
                      'labels': self.labels})

    __getitem__ = __call__

#    def __iter__(self):
#        return self.coordarray.__iter__()


    def __setitem__(self, ixarg, val):
        """Change coordinate array values."""
        ixs = self._force_coords_to_ixlist(ixarg)
        if len(ixs) == 1:
            val = [val]
        try:
            for i, v in zip(ixs,val):
                self.coordarray[i] = v
        except TypeError:
            raise TypeError("Bad value type for Point")


    def toarray(self):
        if self.dimension == 1:
            return self.coordarray[0]
        else:
            return self.coordarray


    def __add__(self, other):
        res = self.copy()
        try:
            res.coordarray += other.coordarray
        except AttributeError:
            res.coordarray += other
        return res

    __radd__ = __add__

    def __sub__(self, other):
        res = self.copy()
        try:
            res.coordarray -= other.coordarray
        except AttributeError:
            res.coordarray -= other
        return res

    def __rsub__(self, other):
        res = self.copy()
        try:
            res.coordarray = other.coordarray - res.coordarray
        except AttributeError:
            res.coordarray = other - res.coordarray
        return res

    def __mul__(self, other):
        res = self.copy()
        try:
            res.coordarray *= other.coordarray
        except AttributeError:
            res.coordarray *= other
        return res

    __rmul__ = __mul__

    def __div__(self, other):
        res = self.copy()
        try:
            res.coordarray /= other.coordarray
        except AttributeError:
            res.coordarray /= other
        return res

    __truediv__ = __div__

    def __rdiv__(self, other):
        res = self.copy()
        try:
            res.coordarray = other.coordarray / res.coordarray
        except AttributeError:
            res.coordarray = other / res.coordarray
        return res

    __rtruediv__ = __rdiv__

    def __pow__(self, other):
        res = self.copy()
        res.coordarray **= other
        return res

    def __neg__(self):
        res = self.copy()
        res.coordarray = - res.coordarray
        return res

    def __pos__(self):
        return self.copy()

    def __lt__(self, other):
        try:
            assert shape(self) == shape(other)
            if hasattr(other, 'coordnames'):
                if self.coordnames != other.coordnames:
                    raise ValueError("Coordinate mismatch")
            return linalg.norm(self.coordarray, self._normord) < \
                   linalg.norm(other.coordarray, self._normord)
        except (AttributeError, TypeError, AssertionError):
            return self.coordarray < other
        except ZeroDivisionError:
            raise ValueError("Norm order for point cannot be zero")

    def __gt__(self, other):
        try:
            assert shape(self) == shape(other)
            if hasattr(other, 'coordnames'):
                if self.coordnames != other.coordnames:
                    raise ValueError("Coordinate mismatch")
            return linalg.norm(self.coordarray, self._normord) > \
                   linalg.norm(other.coordarray, self._normord)
        except (AttributeError, TypeError, AssertionError):
            return self.coordarray > other
        except ZeroDivisionError:
            raise ValueError("Norm order for point cannot be zero")

    def __le__(self, other):
        try:
            assert shape(self) == shape(other)
            if hasattr(other, 'coordnames'):
                if self.coordnames != other.coordnames:
                    raise ValueError("Coordinate mismatch")
            return linalg.norm(self.coordarray, self._normord) <= \
                   linalg.norm(other.coordarray, self._normord)
        except (AttributeError, TypeError, AssertionError):
            return self.coordarray <= other
        except ZeroDivisionError:
            raise ValueError("Norm order for point cannot be zero")

    def __ge__(self, other):
        try:
            assert shape(self) == shape(other)
            if hasattr(other, 'coordnames'):
                if self.coordnames != other.coordnames:
                    raise ValueError("Coordinate mismatch")
            return linalg.norm(self.coordarray, self._normord) >= \
                   linalg.norm(other.coordarray, self._normord)
        except (AttributeError, TypeError, AssertionError):
            return self.coordarray >= other
        except ZeroDivisionError:
            raise ValueError("Norm order for point cannot be zero")

    def __eq__(self, other):
        try:
            assert shape(self) == shape(other)
            if hasattr(other, 'coordnames'):
                if self.coordnames != other.coordnames:
                    raise ValueError("Coordinate mismatch")
            return linalg.norm(self.coordarray, self._normord) == \
                   linalg.norm(other.coordarray, self._normord)
        except (AttributeError, TypeError, AssertionError):
            return self.coordarray == other
        except ZeroDivisionError:
            raise ValueError("Norm order for point cannot be zero")

    def __ne__(self, other):
        try:
            assert shape(self) == shape(other)
            if hasattr(other, 'coordnames'):
                if self.coordnames != other.coordnames:
                    raise ValueError("Coordinate mismatch")
            return linalg.norm(self.coordarray, self._normord) != \
                   linalg.norm(other.coordarray, self._normord)
        except (AttributeError, TypeError, AssertionError):
            return self.coordarray != other
        except ZeroDivisionError:
            raise ValueError("Norm order for point cannot be zero")


    def _infostr(self, verbose=0):
        precision = 8
        if verbose == 0:
            outputStr = "Point with coords:\n"
            for c in self.coordnames:
                outputStr += c
                if c != self.coordnames[-1]:
                    outputStr += "\n"
        elif verbose > 0:
            outputStr = ''
            for c in self.coordnames:
                v = self.coordarray[self._map_names_to_ixs(c)]
                if isinstance(v, ndarray):
                    dvstr = str(v[0])
                else:
                    # only alternative is a singleton numeric value (not list)
                    dvstr = str(v)
                outputStr += c+':  '+dvstr
                if c != self.coordnames[-1]:
                    outputStr += "\n"
            for label, infodict in self.labels.iteritems():
                outputStr += "\nLabels: %s (%s)"%(label, str(infodict))
        return outputStr


    def __repr__(self):
        return self._infostr(verbose=1)


    __str__ = __repr__


    def info(self, verboselevel=1):
        print self._infostr(verboselevel)


    def __abs__(self):
        return linalg.norm(self.coordarray, self._normord)


    def __copy__(self):
        return Point({'coordarray': copy(self.coordarray),
                      'coordnames': copy(self.coordnames),
                      'coordtype': self.coordtype,
                      'norm': self._normord,
                      'labels': self.labels})

    copy = __copy__


    def __getstate__(self):
        d = copy(self.__dict__)
        # remove reference to Cfunc type
        d['coordtype'] = _num_type2name[self.coordtype]
        return d


    def __setstate__(self, state):
        self.__dict__.update(state)
        # reinstate Cfunc type
        self.coordtype = _num_name2type[self.coordtype]


#----------------------------------------------------------------------------


class Pointset(Point):
    """1D parameterized or non-parameterized set of discrete points.
    (If present, the independent variable must be a float64 or an int32)"""

    def __init__(self, kwd=None, **kw):
        if kwd is not None:
            if kw != {}:
                raise ValueError("Cannot mix keyword dictionary and keywords")
            kw = kwd
            if intersect(kw.keys(), point_keys) == []:
                # creating Pointset from dictionary
                temp_kw = {}
                temp_kw['coorddict'] = copy(kw)
                kw = copy(temp_kw)
        # Deal with independent variable, if present
        if 'indepvardict' in kw:
            assert len(kw['indepvardict']) == 1
            try:
                it = kw['indepvartype']
            except KeyError:
                self.indepvartype = float64
            else:
                try:
                    self.indepvartype = _num_equivtype[it]
                except KeyError:
                    raise TypeError('Independent variable type %s not valid'%str(it))
            vals = kw['indepvardict'].values()[0]
            self.indepvarname = kw['indepvardict'].keys()[0]
            if isinstance(vals, _seq_types):
                self.indepvararray = array(vals, self.indepvartype)
            else:
                try:
                    assert self.indepvartype == _num_equivtype[type(vals)]
                except (AssertionError, KeyError):
                    raise TypeError("Invalid type for independent variable value")
                else:
                    self.indepvararray = array([vals], self.indepvartype)
        elif 'indepvararray' in kw:
            if 'indepvarname' in kw:
                self.indepvarname = kw['indepvarname']
            else:
                self.indepvarname = 't'
            vals = kw['indepvararray']
            if isinstance(vals, list):
                try:
                    it = kw['indepvartype']
                except:
                    self.indepvartype = float64
                else:
                    try:
                        self.indepvartype = _num_equivtype[it]
                    except KeyError:
                        raise TypeError('Independent variable type %s not valid'%str(it))
                self.indepvararray = array(vals, self.indepvartype)
            elif isinstance(vals, ndarray):
                # call 'array' constructor to ensure copy is made in case
                # either array is independently changed.
                if rank(vals) == 0:
                    self.indepvararray = array(vals.ravel())
                else:
                    self.indepvararray = array(vals)
                try:
                    self.indepvartype = _num_equivtype[self.indepvararray.dtype.type]
                except KeyError:
                    raise TypeError('Independent variable type '
                                    '%s not valid'%self.indepvararray.dtype)
            else:
                raise TypeError("Invalid type for independent variable "
                                "array: "+str(type(vals)))

        else:
            # non-parameterized case
            self.indepvarname = None
            self.indepvartype = None
            self.indepvararray = None
            self._parameterized = False
        if self.indepvarname:
            # do validation checks
            assert isinstance(self.indepvarname, str), \
                   'independent variable name must be a string'
            try:
                self.indepvartype = _num_equivtype[self.indepvararray.dtype.type]
            except KeyError:
                raise TypeError('Independent variable type '
                                    '%s not valid'%self.indepvararray.dtype)
            r=rank(self.indepvararray)
            if r == 1:
                pass
            elif r == 0:
                self.indepvararray = self.indepvararray.ravel()
            else:
                raise ValueError("Invalid rank for "
                                "independent variable array %i"%r)
            # if user gave independent variable array in reverse order,
            # then we'll reverse this and the coord arrays and the labels
            # at the end of initialization
            do_reverse = not isincreasing(self.indepvararray)
            self._parameterized = True
        # Deal with coordinate data
        if 'coorddict' in kw:
            coorddict = {}
            try:
                ct = kw['coordtype']
            except KeyError:
                self.coordtype = float64
            else:
                try:
                    self.coordtype = _num_equivtype[ct]
                except KeyError:
                    raise TypeError('Coordinate type %s not valid for Point'%str(ct))
            for c, v in kw['coorddict'].iteritems():
                if isinstance(c, str):
                    c_key = c
                else:
                    c_key = repr(c)
                if isinstance(v, list):
                    coorddict[c_key] = array(v, self.coordtype)
                elif isinstance(v, ndarray):
                    # call 'array' constructor on array to ensure it is a copy
                    # if either array is independently changed.
                    coorddict[c_key] = array(v, self.coordtype)
                elif isinstance(v, Pointset):
                    coorddict[c_key] = v.toarray()
                else:
                    try:
                        assert self.coordtype == _num_equivtype[type(v)]
                    except (AssertionError, KeyError):
                        raise TypeError("Must pass arrays, lists, or numeric types")
                    else:
                        coorddict[c_key] = array([v], self.coordtype)
            self.coordnames = coorddict.keys()
            # only way to order dictionary keys for array is to sort
            self.coordnames.sort()
            self.dimension = len(self.coordnames)
            datalist = []
            # loop over coordnames to ensure correct ordering of coordarray
            if self._parameterized:
                my_len = len(self.indepvararray)
            else:
                my_len = len(coorddict[self.coordnames[0]])
            for c in self.coordnames:
                xs = coorddict[c]
                if my_len != len(xs):
                    if self._parameterized:
                        raise ValueError('Independent variable array length must match '
                           'that of each coordinate array')
                    else:
                        raise ValueError('All coordinate arrays must have same length')
                datalist.append(xs)
            self.coordarray = array(datalist, self.coordtype)
            r = rank(self.coordarray)
            if r == 2:
                pass
            elif r == 1:
                self.coordarray = array([self.coordarray], self.coordtype)
            elif r == 0:
                self.coordarray = array([self.coordarray.ravel()], self.coordtype)
            else:
                raise ValueError("Invalid rank for coordinate array: %i"%r)
            assert self.dimension == self.coordarray.shape[0], "Invalid coord array"
        elif 'coordarray' in kw:
            if not isinstance(kw['coordarray'], _seq_types):
                raise TypeError('Coordinate type %s not valid for Pointset'%str(type(kw['coordarray'])))
            try:
                ct = kw['coordtype']
            except KeyError:
                self.coordtype = float64
            else:
                try:
                    self.coordtype = _num_equivtype[ct]
                except KeyError:
                    raise TypeError('Coordinate type %s not valid'%str(ct))
            # calling 'array' constructor creates a copy if original or new
            # array is altered
            array_temp = array(kw['coordarray'], self.coordtype)
            r = rank(array_temp)
            if r == 2:
                self.coordarray = array_temp
            elif r == 1:
                self.coordarray = array([kw['coordarray']], self.coordtype)
            elif r == 0:
                self.coordarray = array([array_temp.ravel()], self.coordtype)
            else:
                raise ValueError("Invalid rank for coordinate array %i"%r)
            self.dimension = self.coordarray.shape[0]
            if 'coordnames' in kw:
                if isinstance(kw['coordnames'], str):
                    coordnames = [kw['coordnames']]
                else:
                    coordnames = kw['coordnames']
            else:
                coordnames = [str(cix) for cix in range(self.dimension)]
            if len(coordnames) != self.dimension:
                print "Pointset initialization error:"
                print "Found Coordnames: ", coordnames, \
                             "(dimension = %s)"%len(coordnames)
                print "vs. data dimension =", self.dimension
                raise ValueError("Mismatch between number of coordnames and "
                                 "dimension of data")
            cs = array(coordnames)
            order = cs.argsort()
            self.coordnames = cs[order].tolist()
            self.coordarray = take(self.coordarray,order,axis=0)
            self.coordtype = self.coordarray.dtype.type
        else:
            raise ValueError("Missing coord info in keywords")
        assert isUniqueSeq(self.coordnames), 'Coordinate names must be unique'
        self.makeIxMaps()
        if self._parameterized:
            assert self.indepvarname not in self.coordnames, \
                   "Independent variable name appeared in coordinate names"
            #            if len(self.coordarray.shape) > 1:
            assert self.coordarray.shape[1] == len(self.indepvararray), \
                   ("Coord array length mismatch with independent variable"
                    " array length")
            #else:
            #    assert self.coordarray.shape[0] == len(self.indepvararray)
            # process choice of indep var tolerance
            if 'checklevel' in kw:
                checklevel = kw['checklevel']
                if checklevel in [0,1]:
                    self.checklevel = checklevel
                else:
                    raise ValueError("Invalid check level")
            else:
                # default to use tolerance in indep val resolution
                self.checklevel = 1
            if 'tolerance' in kw:
                tol = kw['tolerance']
                if tol > 0:
                    self._abseps = tol
                else:
                    raise ValueError("Tolerance must be a positive real number")
            else:
                self._abseps = 1e-13
        if 'name' in kw:
            if isinstance(kw['name'], str):
                self.name = kw['name']
            else:
                raise TypeError("name argument must be a string")
        else:
            self.name = ""
        if 'norm' in kw:
            if kw['norm'] == 0:
                raise ValueError("Norm order for point cannot be zero")
            self._normord = kw['norm']
        else:
            self._normord = 2
        if 'labels' in kw:
            try:
                self.labels = PointInfo(kw['labels'].by_index)
            except AttributeError:
                self.labels = PointInfo(kw['labels'])
        else:
            self.labels = PointInfo()
        if self._parameterized:
            if do_reverse:
                # finish the operation of reversing the reverse-order
                # input arrays
                self.indepvararray = self.indepvararray[::-1]
                self.reverse()
            if not isincreasing(self.indepvararray):
                raise ValueError("Independent variable values must be in "
                                       "increasing order")


    def __delitem__(self, k):
        """Remove point by index or by coordinate."""
        if k in self.coordnames:
            cs = remain(self.coordnames, k)
            p_result = copy(self[cs])
            self.coordnames = cs
            self.coordarray = p_result.coordarray
            self.labels = p_result.labels
            self.indepvararray = p_result.indepvararray
            self.makeIxMaps()
        else:
            # assume integer
            self.remove(k)


    def remove(self, ix):
        """Remove individual Point by its index."""
        if ix == 0:
            try:
                p_result = copy(self[1:])
            except ValueError:
                # slice index out of range => only 1 point left!
                raise ValueError("Cannot remove only point in pointset!")
        else:
            ix = ix % len(self)
            p_result = copy(self[:ix])
            try:
                p_result.append(self[ix+1:])
            except ValueError:
                # ix was at end, so nothing left to append
                pass
        self.coordarray = p_result.coordarray
        self.labels = p_result.labels
        self.indepvararray = p_result.indepvararray
        self.makeIxMaps()


    def reverse(self):
        """Reverse order of points *IN PLACE*."""
        self.coordarray = self.coordarray[:,::-1]
        self.labels.mapIndices(dict(zip(range(0,len(self)),range(len(self)-1,-1,-1))))

    def rename(self, coord, newcoord):
        """Rename a coordinate."""
        try:
            ix = self.coordnames.index(coord)
        except ValueError:
            raise ValueError("No such coordinate: %s"%coord)
        self.coordnames[ix] = newcoord
        self.makeIxMaps()

    def makeIxMaps(self):
        self._name_ix_map = dict(zip(self.coordnames, range(self.dimension)))
        self._ix_name_map = copy(self.coordnames)
        if self._parameterized:
            self._indepvar_ix_map = makeArrayIxMap(self.indepvararray)
        else:
            self._indepvar_ix_map = None


    def addlabel(self, ix, label, info=None):
        """Add string label to indexed point. info dictionary is optional"""
        if ix in range(len(self)):
            self.labels.update(ix, label, info)
        else:
            raise ValueError("Index out of range")


    def removelabel(self, ix):
        """Remove all labels at indexed point."""
        del self.labels[ix]


    def bylabel(self, s):
        """Return pointset containing points labelled with the supplied
        labels. Argument s can be a string or a list of strings."""
        if isinstance(s, str):
            if s == '':
                raise ValueError("Label must be non-empty")
            else:
                ixlist = sortedDictKeys(self.labels[s])
                if ixlist != []:
                    return self[ixlist]
                else:
                    return None
        elif isinstance(s, list):
            ixlist = []
            for ss in s:
                if isinstance(ss, str):
                    if ss == '':
                        raise ValueError("Label must be non-empty")
                    ixlist = sortedDictKeys(self.labels[ss])
                else:
                    raise TypeError("Invalid label type")
            if ixlist != []:
                return self[ixlist]
            else:
                return None
        else:
            raise TypeError("Invalid label type")



    def __setitem__(self, ix, p):
        """Change individual points, accessed by index (no slicing supported).
        Individual coordinate values of a point can be changed by adding a
        cross-reference coordinate name or index.
        If ix is a variable name then the entire row can be changed (again,
        no slicing supported)."""
        if isinstance(ix, _int_types):
            if isinstance(p, Point):
                if compareNumTypes(self.coordtype, int32) and \
                   compareNumTypes(p.coordtype, float64):
                    raise ValueError("Cannot update integer pointset with a float")
                self.coordarray[:,ix] = p.toarray()
                if len(p.labels) > 0:
                    self.labels.update({ix: p.labels})
            elif isinstance(p, dict):
                vlist = []
                for k in self.coordnames:
                    vlist.append(p[k])
                self.coordarray[:,ix] = array(vlist, self.coordtype)
            elif isinstance(p, _seq_types):
                self.coordarray[:,ix] = array(p, self.coordtype)
            else:
                raise TypeError("Invalid index reference")
        elif isinstance(ix, tuple) and len(ix) == 2:
            # note that index order must be reversed
            try:
                c = self._name_ix_map[ix[1]]
            except KeyError:
                c = ix[1]
            if isinstance(p, _int_types):
                self.coordarray[c,ix[0]] = p
            elif isinstance(p, _float_types):
                if self.coordtype == float64:
                    self.coordarray[c,ix[0]] = p
                else:
                    raise TypeError("Cannot update an integer pointset with a float")
            elif isinstance(p, ndarray) and p.shape==(1,):
                self.coordarray[c,ix[0]] = p[0]
            elif isinstance(p, list) and len(list) == 1:
                self.coordarray[c,ix[0]] = p[0]
            elif isinstance(p, Point) and p.dimension == 1:
                self.coordarray[c,ix[0]] = p[0]
                if len(p.labels) > 0:
                    self.labels.update({ix: p.labels})
            else:
                raise TypeError("New value is not a singleton numeric type")
        elif isinstance(ix, str):
            if ix == self.indepvarname:
                if isinstance(p, Pointset):
                    if compareNumTypes(self.indepvartype, int32) and \
                       compareNumTypes(p.indepvartype, float64):
                        raise ValueError("Cannot update integer independent variable with a float")
                    if len(self) == len(p):
                        self.indepvararray = p.toarray()
                    else:
                        raise ValueError("Size mismatch for new independent variable array")
                    # labels ignored
                elif isinstance(p, dict):
                    if len(self) == len(p[c]):
                        self.indepvararray = array(p[c], self.indepvartype)
                    else:
                        raise ValueError("Size mismatch for new independent variable array")
                elif isinstance(p, _seq_types):
                    if len(self) == len(p):
                        self.indepvararray = array(p, self.indepvartype)
                    else:
                        raise ValueError("Size mismatch for new independent variable array")
                else:
                    raise TypeError("Invalid data")
            elif ix in self.coordnames:
                c = self._name_ix_map[ix]
                if isinstance(p, Pointset):
                    if compareNumTypes(self.coordtype, int32) and \
                       compareNumTypes(p.coordtype, float64):
                        raise ValueError("Cannot update integer pointset with a float")
                    self.coordarray[c,:] = p.toarray()
                    # labels ignored
                elif isinstance(p, dict):
                    self.coordarray[c,:] = array(p[c], self.coordtype)
                elif isinstance(p, _seq_types):
                    self.coordarray[c,:] = array(p, self.coordtype)
                elif isinstance(p, _real_types):
                    self.coordarray[c,:] = float(p)
                else:
                    raise TypeError("Invalid data")
            else:
                raise TypeError("Invalid variable reference")
        else:
            raise TypeError("Invalid Pointset reference")


    def __getitem__(self, ix):
        # select points
        if isinstance(ix, _int_types):
            # The labels (PointInfo) object doesn't understand -ve indices,
            # but don't take modulo length otherwise iteration will break
            if ix < 0:
                ix = ix + self.coordarray.shape[1]
            if ix in self.labels:
                label = self.labels[ix]
            else:
                label = {}
            return Point({'coordarray': self.coordarray[:,ix],
                          'coordnames': self.coordnames,
                          'norm': self._normord,
                          'labels': label})
        elif isinstance(ix, tuple):
            if len(ix) != 2:
                raise ValueError("Only use 2-tuples in referencing pointset")
            ref1 = ix[0]
            ref2 = ix[1]
        elif isinstance(ix, str):
            # reference by coord name
            if self._parameterized:
                if ix == self.indepvarname:
                    return self.indepvararray
                else:
                    return self.coordarray[self._map_names_to_ixs(ix),:]
            else:
                return self.coordarray[self._map_names_to_ixs(ix),:]
        elif isinstance(ix, list):
            if all([x in self.coordnames for x in ix]):
                ref1 = slice(len(self))
                ref2 = ix
            else:
                ref1 = ix
                ref2 = None
        elif isinstance(ix, (ndarray, slice)):
            ref1 = ix
            ref2 = None
        else:
            raise IndexError("Illegal index %s"%str(ix))
        if isinstance(ref1, (list, ndarray, _int_types)):
            if isinstance(ref1, _int_types):
                ref1 = [ref1]
            try:
                ca = take(self.coordarray, ref1, axis=1)
            except ValueError:
                raise ValueError("Invalid variable names given: "%(str(ref1)))
            try:
                ci = take(self.indepvararray, ref1, axis=0)
            except (IndexError, AttributeError):
                # non-parameterized pointset
                pass
            cl = self.labels[ref1]
            cl_ixs = cl.getIndices()
            ixmap = invertMap(ref1)
            new_cl_ixs = [ixmap[i] for i in cl_ixs]
        elif isinstance(ref1, slice):
            ls = len(self)
            if ref1.stop is None:
                stop = ls
            else:
                if ref1.stop < 0:
                    stop = ref1.stop + self.coordarray.shape[1] + 1
                else:
                    stop = ref1.stop
            s1, s2, s3 = ref1.indices(stop)
            if s1 < 0 or s2 > ls or s1 >= ls:
                raise ValueError("Slice index out of range")
            ca = take(self.coordarray, xrange(s1, s2, s3), axis=1)
            try:
                ci = take(self.indepvararray, xrange(s1, s2, s3),axis=0)
            except (IndexError, AttributeError):
                # non-parameterized pointset
                pass
            cl = self.labels[ref1]
            cl_ixs = cl.getIndices()
            lowest_ix = ref1.start or 0
            if lowest_ix < 0:
                lowest_ix = len(self)+lowest_ix
            new_cl_ixs = [i-lowest_ix for i in cl_ixs]
        else:
            print "ref1 argument =", ref1
            raise TypeError("Type %s is invalid for Pointset indexing"%str(type(ref1)))
        ixlist = self._force_coords_to_ixlist(ref2)
        ca = take(ca, ixlist, axis=0)
        try:
            cl.mapIndices(dict(zip(cl_ixs, new_cl_ixs)))
        except AttributeError:
            pass
        if self._parameterized:
            return Pointset({'coordarray': ca,
                             'coordnames': [self.coordnames[i] for i in ixlist],
                             'indepvararray': ci,
                             'indepvarname': self.indepvarname,
                             'norm': self._normord,
                             'labels': cl})
        else:
            return Pointset({'coordarray': ca,
                            'coordnames': [self.coordnames[i] for i in ixlist],
                            'norm': self._normord,
                            'labels': cl})


    def _resolve_indepvar(self, p):
        if self.checklevel == 0:
            return self._indepvar_ix_map[p]
        else:
            try:
                return self._indepvar_ix_map[p]
            except:
                ixs = self.findIndex(p)
                lval = self.indepvararray[ixs[0]]
                rval = self.indepvararray[ixs[1]]
                if p - lval < self._abseps:
                    return ixs[0]
                elif rval - p <= self._abseps:
                    return ixs[1]
                else:
                    lerr = p - lval
                    rerr = rval - p
                    raise KeyError( \
                  "%f not found in (%f, %f) @tol=%.16f: mismatches=(%.16f, %.16f)"%(p,lval,rval,self._abseps,lerr,rerr))


    def setTol(self, tol):
        if tol > 0:
            self._abseps = tol
        else:
            raise ValueError("tolerance must be a positive real number")


    def __call__(self, p, coords=None):
        if not self._parameterized:
            raise TypeError("Cannot call a non-parameterized Pointset")
        if isinstance(p, _seq_types):
            # assume p is an all-numeric list, so it should be treated as
            # an independent variable.
            try:
                ix = [self._resolve_indepvar(i) for i in p]
            except KeyError:
                raise ValueError("Independent variable value not valid: %s"%str(p))
        else:
            # assume p is an integer or float, appropriate to independent var
            try:
                ix = self._resolve_indepvar(p)
            except KeyError:
                raise ValueError("Independent variable value not valid: " \
                                 + str(p))
        if coords is None:
            if isinstance(ix, _int_types):
                label = self.labels[ix]
                try:
                    label.mapIndices({ix: 0})
                except AttributeError:
                    # empty
                    pass
                return Point({'coordarray': self.coordarray[:,ix],
                              'coordnames': self.coordnames,
                              'norm': self._normord,
                              'labels': label})
            else:
                labels = self.labels[ix]
                cl_ixs = labels.getIndices()
                ixmap = invertMap(ix)
                new_cl_ixs = [ixmap[i] for i in cl_ixs]
                if isinstance(ix, slice):
                    lowest_ix = ix.start or 0
                    new_cl_ixs = [i-lowest_ix for i in cl_ics]
                elif isinstance(ix, (list, ndarray)):
                    new_cl_ixs = [ixmap[i] for i in cl_ixs]
                try:
                    labels.mapIndices(dict(zip(cl_ixs, new_cl_ixs)))
                except AttributeError:
                    # empty
                    pass
                return Pointset({'coordarray': take(self.coordarray, ix, axis=1),
                         'coordnames': self.coordnames,
                         'indepvarname': self.indepvarname,
                         'indepvararray': take(self.indepvararray, ix, axis=0),
                         'norm': self._normord,
                         'labels': labels})
        else:
            clist = self._force_coords_to_ixlist(coords)
            if isinstance(ix, _int_types):
                label = self.labels[ix]
                try:
                    label.mapIndices({ix: 0})
                except AttributeError:
                    # empty
                    pass
                return Point({'coordarray': self.coordarray[clist, ix],
                          'coordnames': [self.coordnames[i] for i in clist],
                          'norm': self._normord,
                          'labels': label})
            else:
                labels = self.labels[ix]
                try:
                    labels.mapIndices(dict(zip(labels, [i-ix[0] for i in labels.getIndices()])))
                except AttributeError:
                    # empty
                    pass
                return Pointset({'coordarray': take(self.coordarray[clist], ix, axis=1),
                                 'coordnames': [self.coordnames[i] for i in clist],
                                 'indepvarname': self.indepvarname,
                                 'indepvararray': take(self.indepvararray, ix, axis=0),
                                 'norm': self._normord,
                                 'labels': labels})


    def __len__(self):
        return self.coordarray.shape[1]


    def __contains__(self, other):
        for i in xrange(len(self)):
            if comparePointCoords(self.__getitem__(i), other):
                return True
        return False


    def __lt__(self, other):
        if isinstance(other, Pointset):
            if not all(self.indepvararray == other.indepvararray):
                raise ValueError("Independent variable arrays are not the same")
            return array([self[i] < other[i] for i in range(len(self))], 'Bool')
        elif isinstance(other, Point):
            return array([p < other for p in self], 'Bool')
        else:
            try:
                return self.coordarray < other
            except:
                raise TypeError("Invalid type for comparison with Pointset")

    def __gt__(self, other):
        if isinstance(other, Pointset):
            if not all(self.indepvararray == other.indepvararray):
                raise ValueError("Independent variable arrays are not the same")
            return array([self[i] > other[i] for i in range(len(self))], 'Bool')
        elif isinstance(other, Point):
            return array([p > other for p in self], 'Bool')
        else:
            try:
                return self.coordarray > other
            except:
                raise TypeError("Invalid type for comparison with Pointset")

    def __le__(self, other):
        if isinstance(other, Pointset):
            if not all(self.indepvararray == other.indepvararray):
                raise ValueError("Independent variable arrays are not the same")
            return array([self[i] <= other[i] for i in range(len(self))], 'Bool')
        elif isinstance(other, Point):
            return array([p <= other for p in self], 'Bool')
        else:
            try:
                return self.coordarray <= other
            except:
                raise TypeError("Invalid type for comparison with Pointset")

    def __ge__(self, other):
        if isinstance(other, Pointset):
            if not all(self.indepvararray == other.indepvararray):
                raise ValueError("Independent variable arrays are not the same")
            return array([self[i] >= other[i] for i in range(len(self))], 'Bool')
        elif isinstance(other, Point):
            return array([p >= other for p in self], 'Bool')
        else:
            try:
                return self.coordarray >= other
            except:
                raise TypeError("Invalid type for comparison with Pointset")

    def __eq__(self, other):
        if isinstance(other, Pointset):
            if not all(self.indepvararray == other.indepvararray):
                raise ValueError("Independent variable arrays are not the same")
            return array([self[i] == other[i] for i in range(len(self))], 'Bool')
        elif isinstance(other, Point):
            return array([p == other for p in self], 'Bool')
        else:
            try:
                return self.coordarray == other
            except:
                raise TypeError("Invalid type for comparison with Pointset")

    def __ne__(self, other):
        if isinstance(other, Pointset):
            if not all(self.indepvararray == other.indepvararray):
                raise ValueError("Independent variable arrays are not the same")
            return array([self[i] != other[i] for i in range(len(self))], 'Bool')
        elif isinstance(other, Point):
            return array([p != other for p in self], 'Bool')
        else:
            try:
                return self.coordarray != other
            except:
                raise TypeError("Invalid type for comparison with Pointset")


    def insert(self, parg, ix=None):
        """Insert individual Point or Pointset before the given index.

        If ix is not given then the source and target Pointsets must
        be parameterized. In this case the Point or Pointset will be
        inserted according to the ordering of independent variable
        values."""
        p=copy(parg)
        if ix is None:
            if self._parameterized:
                if isinstance(p, Point) and self.indepvarname in p.coordnames:
                    t = p[self.indepvarname]
                    tix = self.find(t)
                    if isinstance(tix, tuple):
                        self.insert(p, tix[1])
                    else:
                        # tix was an integer, meaning that t is
                        # already present in Pointset
                        raise ValueError("Point at independent variable"
                                         "value %f already present"%t)
                elif isinstance(p, Pointset) and p._parameterized and \
                       p.indepvarname == self.indepvarname:
                    # Don't do a straight self.insert call in case the
                    # new indep var values need to be interleaved with
                    # the present ones.
                    #
                    # convert self.indepvararray and self.coordarray into lists (by self.todict())
                    iva = self.indepvararray.tolist()
                    vd = self.todict(aslist=True)
                    # get list of findIndex results for each of p indepvar vals
                    # add i for each one because each previous one will have been inserted,
                    # increasing the length of self.
                    if len(intersect(self._ix_name_map, p._ix_name_map)) != self.dimension:
                        raise ValueError("Dimension mismatch with inserted Pointset")
                    iva_p = p.indepvararray
                    lenp = len(p)
                    vd_p = p.todict()
                    try:
                        s_ixs = [self.findIndex(iva_p[i])[1]+i for i in xrange(lenp)]
                    except TypeError:
                        raise ValueError("Independent variable "
                                         "values in Pointset already present")
                    p_label_ixs = p.labels.getIndices()
                    s_label_ixs = self.labels.getIndices()
                    sLabelMap = {}
                    pLabelMap = {}
                    for i in xrange(lenp):
                        s_ix = s_ixs[i]
                        if i in p_label_ixs:
                            pLabelMap[i] = s_ix
                        for s_label_ix in s_label_ixs:
                            if s_label_ix >= s_ix-i:
                                sLabelMap[s_label_ix] = s_label_ix+i+1
                    # for each one, list-insert new point data
                    for p_ix in xrange(lenp):
                        s_ix = s_ixs[p_ix]
                        iva.insert(s_ix, iva_p[p_ix])
                        for k in self._ix_name_map:
                            vd[k].insert(s_ix, vd_p[k][p_ix])
                    # restore self's arrays
                    self.indepvararray = array(iva)
                    datalist = []
                    for c in p._ix_name_map:
                        datalist.append(vd[c])
                    self.coordarray = array(datalist, self.coordtype)
                    # update labels
                    self.labels.mapIndices(sLabelMap)
                    p_labels = copy(p.labels)
                    p_labels.mapIndices(pLabelMap)
                    self.labels.update(p_labels)
                else:
                    raise TypeError("Inserted Point/Pointset must be "
                                    "parameterized and share same independent"
                                    "parameter name")
            else:
                raise TypeError("Source Pointset must be parameterized")
        else:
            if ix > 0:
                p_result = copy(self[:ix])
                p_result.append(p)
            else:
                p_result = pointsToPointset(p, self.indepvarname)
            try:
                p_result.append(self[ix:])
            except ValueError:
                # ix > greatest index, so no points left to add
                # (i.e., p was appended to end)
                pass
            self.coordarray = p_result.coordarray
            self.labels = p_result.labels
            self.indepvararray = p_result.indepvararray
        self.makeIxMaps()


    def append(self, parg, t=None, skipMatchingIndepvar=False):
        """Append individual Point or Pointset in place.

        skipMatchingIndepvar option causes a matching independent
        variable value at the beginning of p to be skipped (only
        meaningful for appending parameterized Pointsets). This
        option is mainly for internal use."""

        # test isinstance for Pointset first because it is a sub-class of Point
        # and so isinstance(p, Point) will also catch Pointsets!
        p = copy(parg)
        if isinstance(p, Pointset):
            assert p._parameterized == self._parameterized, "Parameterization mismatch"
            # check p dimension and coordnames and type
            if compareNumTypes(self.coordtype, int32) and \
               compareNumTypes(p.coordtype, float64):
                raise TypeError("Cannot add float64 pointset to an int32 Pointset")
            pdim = p.dimension
            if self._parameterized:
                if t is None:
                    if self.indepvarname in p.coordnames:
                        t = p[self.indepvarname]
                        pdim = pdim - 1
                    elif self.indepvarname == p.indepvarname:
                        t = p.indepvararray
                    else:
                        raise ValueError("Independent variable missing from Pointset")
                    if t[0] == self.indepvararray[-1] and skipMatchingIndepvar:
                        tval = t[1:]
                        start_ix = 1
                    else:
                        tval = t
                        start_ix = 0
                    if len(tval) > 0 and tval[0] <= self.indepvararray[-1]:
                        #print tval[0], " <= ", self.indepvararray[-1]
                        raise ValueError("Independent variable value too small to add pointset")
                    added_len = len(tval)
                else:
                    if t[0] == self.indepvararray[-1] and skipMatchingIndepvar:
                        tval = t[1:]
                        start_ix = 1
                    else:
                        tval = t[:]  # ensures tval is an array (t might be a Pointset)
                        start_ix = 0
                    if len(tval) > 0 and tval[0] <= self.indepvararray[-1]:
                        #print tval[0], " <= ", self.indepvararray[-1]
                        raise ValueError("Independent variable value too small to add pointset")
                    added_len = len(tval)
            else:
                if t is not None:
                    raise TypeError("t argument cannot be used for non-parameterized pointsets")
                added_len = p.coordarray.shape[1]
                start_ix = 0
            assert pdim == self.dimension, "Dimension mismatch with Pointset"
            if pdim < p.dimension:
                pcoords = copy(p.coordnames)
                pcoords.remove(p.indepvarname)
            else:
                pcoords = p.coordnames
            if remain(pcoords, self.coordnames) != []:
                raise ValueError("Coordinate name mismatch with Pointset")
            old_len = self.coordarray.shape[1]
            new_len = old_len + added_len
            old_coords = self.coordarray
            self.coordarray = zeros((self.dimension, new_len),
                                    self.coordarray.dtype)
            if self._parameterized:
                self.indepvararray.resize(new_len)
                tvals = tval[range(added_len)]
                self.indepvararray[old_len:] = tvals
            for tix in xrange(old_len):
                self.coordarray[:, tix] = old_coords[:, tix]
            pdict = p.todict()
            self.coordarray[:, old_len:] = r_[[pdict[c][start_ix:] for c in self._ix_name_map]]
            p_labels = copy(p.labels)
            pixs = p.labels.getIndices()
            if start_ix == 1:
                p_labels.mapIndices(dict(zip(pixs, [i+old_len-1 for i in pixs])))
            else:
                p_labels.mapIndices(dict(zip(pixs, [i+old_len for i in pixs])))
            self.labels.update(p_labels)
        elif isinstance(p, Point):
            # check p dimension and coordnames and type
            if compareNumTypes(self.coordtype, int32) and \
               compareNumTypes(p.coordtype, float64):
                raise TypeError("Cannot add float64 Point to an int32 Pointset")
            pdim = p.dimension
            if self._parameterized:
                if t is None:
                    if self.indepvarname not in p.coordnames:
                        raise ValueError("Independent variable missing from Point")
                    else:
                        tval = p[self.indepvarname]
                        if tval <= self.indepvararray[-1]:
                            raise ValueError("Independent variable value too small to add Point")
                        pdim = pdim - 1
                else:
                    if t <= self.indepvararray[-1]:
                        raise ValueError("Independent variable value too small to add Point")
                    tval = t
            elif t is not None:
                raise TypeError("t argument cannot be used for non-parameterized Pointsets")
            assert pdim == self.dimension, "Dimension mismatch with Point"
            if pdim < p.dimension:
                pcoords = copy(p.coordnames)
                if self._parameterized:
                    pcoords.remove(self.indepvarname)
            else:
                pcoords = p.coordnames
            if remain(pcoords, self.coordnames) != []:
                raise ValueError("Coordinate name mismatch with Point")
            new_len = self.coordarray.shape[1]+1
            old_coords = self.coordarray
            self.coordarray = zeros((self.dimension, new_len), self.coordarray.dtype)
            if self._parameterized:
                self.indepvararray.resize(new_len)
                self.indepvararray.resize(new_len)
                self.indepvararray[new_len-1] = tval
            for tix in xrange(new_len-1):
                self.coordarray[:, tix] = old_coords[:, tix]
            for ix in xrange(self.dimension):
                self.coordarray[ix,new_len-1] = p(self._ix_name_map[ix])
            if len(p.labels) > 0:
                self.labels.update({new_len-1: p.labels})
        else:
            raise TypeError("append requires Point or Pointset argument")
        self.makeIxMaps()


    extend = append   # for intuitive compatibility!


    def toarray(self):
        if self.dimension==1:
            return self.coordarray[0]
        else:
            return self.coordarray


    def todict(self, aslist=False):
        """Convert Pointset to a dictionary of arrays (or of lists with aslist=True)."""
        if aslist:
            d = dict(zip(self._ix_name_map, self.coordarray.tolist()))
        else:
            d = dict(zip(self._ix_name_map, self.coordarray))
            if self._parameterized:
                d[self.indepvarname] = self.indepvararray
        return d


    def _infostr(self, verbose=0):
        if self.name == '':
            outputStr = "Pointset <no name>"
        else:
            outputStr = "Pointset " + self.name
        if self._parameterized:
            outputStr += " (parameterized)"
        else:
            outputStr += " (non-parameterized)"
        if verbose > 0:
            precision = 8
            lenv = len(self)
            if lenv > 8:
                ixslo = range(0,2)
                ixshi = range(lenv-2,lenv)
            outputStr += "\n"
            if self._parameterized:
                iv = self.indepvararray
                if not isinstance(iv, ndarray):
                    iv = array(iv, self.indepvartype)  # permits slicing (lists don't)
                if lenv > 8:
                    alo = array2string(iv[ixslo],precision=precision)
                    ahi = array2string(iv[ixshi],precision=precision)
                    ivstr = alo[:-1] + ", ..., " + ahi[1:]
                else:
                    ivstr = array2string(iv,precision=precision)
                outputStr += "Independent variable:\n"
                outputStr += self.indepvarname + ':  '+ivstr+"\n"
            outputStr += "Coordinates:\n"
            for c in self.coordnames:
                v = self.coordarray[self._map_names_to_ixs(c)]
                if not isinstance(v, ndarray):
                    # only alternative is a singleton numeric value (not a list)
                    v = array([v], self.coordtype)
                if lenv > 8:
                    alo = array2string(v[ixslo],precision=precision)
                    ahi = array2string(v[ixshi],precision=precision)
                    dvstr = alo[:-1] + ", ..., " + ahi[1:]
                else:
                    dvstr = array2string(v, precision=precision)
                outputStr += c+':  '+dvstr
                if c != self.coordnames[-1]:
                    outputStr += "\n"
            outputStr += "\nLabels by index: " + self.labels._infostr(17)
        return outputStr


    def __repr__(self):
        return self._infostr(verbose=1)


    def __str__(self):
        return self._infostr(verbose=0)


    def info(self, verboselevel=1):
        print self._infostr(verboselevel)


    def __copy__(self):
        if self._parameterized:
            return Pointset({'coordarray': copy(self.coordarray),
                         'coordnames': copy(self.coordnames),
                         'indepvarname': copy(self.indepvarname),
                         'indepvararray': copy(self.indepvararray),
                         'norm': self._normord,
                         'labels': copy(self.labels)
                         })
        else:
            return Pointset({'coordarray': copy(self.coordarray),
                         'coordnames': copy(self.coordnames),
                         'norm': self._normord,
                         'labels': copy(self.labels)})

    copy = __copy__


    def __getstate__(self):
        d = copy(self.__dict__)
        # remove reference to Cfunc types by converting them to strings
        try:
            d['indepvartype'] = _num_type2name[self.indepvartype]
        except KeyError:
            # non-parameterized Pointset
            pass
        d['coordtype'] = _num_type2name[self.coordtype]
        return d


    def __setstate__(self, state):
        self.__dict__.update(state)
        # reinstate Cfunc types
        try:
            self.indepvartype = _num_name2type[self.indepvartype]
        except KeyError:
            # non-parameterized Pointset
            pass
        self.coordtype = _num_name2type[self.coordtype]

    def _match_indepvararray(self, other):
        """Verifies the matching of independent variable arrays in two pointsets.
        Does nothing if either object is not a parameterized pointset."""
        try:
            if other._parameterized and self._parameterized:
                if not all(self.indepvararray == other.indepvararray):
                    print self.indepvararray
                    print other.indepvararray
                    raise ValueError("Mismatched independent variable arrays")
        except AttributeError:
            pass

    def __add__(self, other):
        self._match_indepvararray(other)
        return Point.__add__(self, other)

    def __radd__(self, other):
        self._match_indepvararray(other)
        return Point.__radd__(self, other)

    def __sub__(self, other):
        self._match_indepvararray(other)
        return Point.__sub__(self, other)

    def __rsub__(self, other):
        self._match_indepvararray(other)
        return Point.__rsub__(self, other)

    def __mul__(self, other):
        self._match_indepvararray(other)
        return Point.__mul__(self, other)

    def __rmul__(self, other):
        self._match_indepvararray(other)
        return Point.__rmul__(self, other)

    def __div__(self, other):
        self._match_indepvararray(other)
        return Point.__div__(self, other)

    def __rdiv__(self, other):
        self._match_indepvararray(other)
        return Point.__rdiv__(self, other)

    def find(self, indepval, end=None):
        """find returns an integer index for where to place
        a point having independent variable value <indepval> in
        the Pointset, if <indepval> already exists. Otherwise, a
        pair indicating the nearest independent variable values
        present in the Pointset is returned.

        To ensure an integer is always returned, choose a left or
        right side to choose from the pair, using end=0 or 1 respectively."""
        if not self._parameterized:
            raise TypeError("Cannot find index from independent variable for "
                            "a non-parameterized Pointset")
        try:
            ix = self.indepvararray.tolist().index(indepval)
            result = ix
        except ValueError:
            cond = less(self.indepvararray, indepval).tolist()
            try:
                ix = cond.index(0)
                result = (ix-1, ix)
            except ValueError:
                result = (len(self.indepvararray)-1, len(self.indepvararray))
            if end is not None:
                result = result[end]
        return result

    # deprecated
    findIndex = find


# ----------------------------------------------------------------------------


class PointInfo(object):
    """Structure for storing individual point labels and information
    dictionaries within a Pointset object.

    This class will not know the size of the Pointset it is associated with,
    so index upper limits will not be checked in advance.

    Do not use a PointInfo object as an iterator, as it is 'infinite' in size!
    (It uses DefaultDicts as its internal storage, which return {} for
    undefined labels.)"""

    def __init__(self, ptlabels=None):
        if ptlabels is None:
            self.by_label = DefaultDict({})
            self.by_index = DefaultDict({})
        elif isinstance(ptlabels, PointInfo):
            self.by_label = ptlabels.by_label
            self.by_index = ptlabels.by_index
        elif isinstance(ptlabels, dict):
            # always expect the dictionary to be based on index
            self.by_label = DefaultDict({})
            self.by_index = DefaultDict({})
            for k, v in ptlabels.iteritems():
                if not isinstance(k, _int_types):
                    raise TypeError("Initialization dictionary must be keyed "
                                    "by integer indices")
                if isinstance(v, str):
                    self.by_label[v][k] = {}
                    self.by_index[k][v] = {}
                else:
                    for label, infodict in v.iteritems():
                        self.by_label[label][k] = infodict
                        self.by_index[k][label] = infodict
        else:
            raise TypeError("Invalid labels at initialization of PointInfo")


    def mapIndices(self, ixMapDict):
        by_index = {}
        ixMap = symbolMapClass(ixMapDict)
        for ix, rest in self.by_index.iteritems():
            by_index[ixMap(ix)] = rest
        self.__init__(by_index)


    def mapNames(self, themap):
        """Map labels, using a symbol map of class symbolMapClass."""
        self.by_label = mapNames(themap, self.by_label)
        new_by_index = {}
        for ix, labdict in self.by_index.iteritems():
            new_by_index[ix] = mapNames(themap, labdict)
        self.by_index = new_by_index


    def sortByIndex(self):
        ixkeys = sortedDictKeys(self.by_index)
        return zip(ixkeys,[self.by_index[ix] for ix in ixkeys])


    def sortByLabel(self):
        labelkeys = sortedDictKeys(self.by_label)
        return zip(labelkeys,[self.by_label[label] for label in labelkeys])


    def getIndices(self):
        return sortedDictKeys(self.by_index)


    def getLabels(self):
        return sortedDictKeys(self.by_label)


    def __contains__(self, key):
        return key in self.by_index or key in self.by_label


    def __getitem__(self, key):
        # indices already are enforced to be integers, and labels strings,
        # so this is a safe way to search!
        # Note: if don't use if-then test then DefaultDict will
        # create an empty entry for the failed key when .values() is called!
        if isinstance(key, tuple):
            raise TypeError("Can only reference PointInfo with a single key")
        else:
            if isinstance(key, (slice, list, ndarray)):
                if isinstance(key, slice):
                    self_ixs = self.getIndices()
                    if len(self_ixs) == 0:
                        max_ixs = 0
                    else:
                        max_ixs = max(self_ixs)
                    stop = key.stop or max_ixs+1
                    try:
                        s1, s2, s3 = key.indices(stop)
                        ixs = xrange(s1, s2, s3)
                        key = intersect(ixs, self_ixs)
                    except TypeError:
                        key = self_ixs
                else:
                    if all([isinstance(k, str) for k in key]):
                        keylabels = intersect(key, self.getLabels())
                        key = []
                        for l in keylabels:
                            key.extend(self.by_label[l].keys())
                        key = makeSeqUnique(key)
                    elif all([isinstance(k, _int_types) for k in key]):
                        key = intersect(key, self.getIndices())
                    else:
                        raise TypeError("Invalid key type for PointInfo")
                return PointInfo(dict(zip(key,[self.by_index[i] for i in key])))
            elif key in self.by_index:
                return self.by_index[key]
            elif key in self.by_label:
                return self.by_label[key]
            elif isinstance(key, int) and key < 0:
                raise IndexError("Cannot use negative indices for PointInfo")
            else:
                return {}


    def __setitem__(self, key1, the_rest):
        if isinstance(the_rest, tuple) and len(the_rest) == 2:
            if isinstance(the_rest[0], str):
                label = the_rest[0]
                ix = None
            elif isinstance(the_rest[0], _int_types):
                ix = the_rest[0]
                label = None
            else:
                raise TypeError("String expected for label")
            if isinstance(the_rest[1], dict):
                info = copy(the_rest[1])
            else:
                raise TypeError("Dictionary expected for info")
        elif isinstance(the_rest, str):
            label = the_rest
            ix = None
            info = {}
        elif isinstance(the_rest, _int_types):
            ix = the_rest
            label = None
            info = {}
        elif isinstance(the_rest, list):
            self.__setitem__(key1, the_rest[0])
            for item in the_rest[1:]:
                if isinstance(item, tuple) and len(item) == 2:
                    self.update(key1, item[0], item[1])
                else:
                    self.update(key1, item)
            return
        else:
            raise TypeError("Invalid item to set in PointInfo")
        if isinstance(key1, _int_types):
            if label is None:
                raise TypeError("Label expected")
            ix = key1
        elif isinstance(key1, str):
            if ix is None:
                raise TypeError("Index expected")
            label = key1
        if ix < 0:
            raise IndexError("Index must be non-negative")
        try:
            self.by_label[label].update({ix: info})
        except KeyError:
            self.by_label[label] = {ix: info}
        try:
            self.by_index[ix].update({label: info})
        except KeyError:
            self.by_index[ix] = {label: info}


    def __len__(self):
        return len(self.by_index)


    def remove(self, key1, *key2):
        """remove one or more items, keyed either by index or label."""
        byix = key1 in self.by_index
        if key2 == ():
            # remove all labels associated with index, or vice versa
            if byix:
                key2 = self.by_index[key1].keys()
            else:
                key2 = self.by_label[key1].keys()
        if byix:
            for k in key2:
                # have to check k in dict otherwise DefaultDict creates entry!
                if k in self.by_label:
                    del self.by_index[key1][k]
                    del self.by_label[k][key1]
                else:
                    raise KeyError("Label not found")
                if self.by_label[k] == {}:
                    del self.by_label[k]
            if self.by_index[key1] == {}:
                del self.by_index[key1]
        else:
            for k in key2:
                # have to check k in dict otherwise DefaultDict creates entry!
                if k in self.by_index:
                    del self.by_index[k][key1]
                    del self.by_label[key1][k]
                else:
                    raise KeyError("Index not found")
                if self.by_index[k] == {}:
                    del self.by_index[k]
            if self.by_label[key1] == {}:
                del self.by_label[key1]


    def update(self, key1, key2=None, info=None):
        if isinstance(key1, PointInfo):
            if key2 is None and info is None:
                for k, v in key1.by_index.iteritems():
                    for vk, vv in v.iteritems():
                        self.update(k, vk, vv)
            else:
                raise TypeError("Invalid calling sequence to update")
        elif isinstance(key1, dict):
            if key2 is None and info is None:
                for k, v in key1.iteritems():
                    if isinstance(k, _int_types) and k >= 0:
                        if isinstance(v, str):
                            k2 = v
                            k3 = {}
                            self.update(k, k2, k3)
                        elif isinstance(v, tuple) and len(v)==2:
                            k2 = v[0]
                            k3 = v[1]
                            self.update(k, k2, k3)
                        elif isinstance(v, dict):
                            for k2, k3 in v.iteritems():
                                self.update(k, k2, k3)
                        else:
                            raise ValueError("Invalid data for update")
                    else:
                        raise TypeError("Invalid index for label")
            else:
                raise TypeError("Invalid calling sequence to update")
        elif isinstance(key1, _int_types):
            if info is None:
                info = {}
            if key1 in self.by_index:
                if key2 in self.by_index[key1]:
                    self.by_index[key1][key2].update(info)
                else:
                    self.__setitem__(key1, (key2, info))
            else:
                self.__setitem__(key1, (key2, info))
        elif isinstance(key1, str):
            if info is None:
                info = {}
            if key1 in self.by_label:
                if key2 in self.by_label[key1]:
                    self.by_label[key1][key2].update(info)
                else:
                    self.__setitem__(key2, (key1, info))
            else:
                self.__setitem__(key2, (key1, info))
        else:
            raise TypeError("Invalid type for update")


    def __delitem__(self, key):
        if key in self.by_index:
            labels = self.by_index[key].keys()
            del self.by_index[key]
            for label in labels:
                del self.by_label[label][key]
                if self.by_label[label] == {}:
                    del self.by_label[label]
        elif key in self.by_label:
            ixs = self.by_label[key].keys()
            del self.by_label[key]
            for ix in ixs:
                del self.by_index[ix][key]
                if self.by_index[ix] == {}:
                    del self.by_index[ix]
        else:
            raise KeyError("Index or label not found")


    def __eq__(self, other):
        try:
            return all(self.by_index.keys() == other.by_index.keys()) and \
                   all(self.by_label.keys() == other.by_label.keys())
        except AttributeError:
            raise TypeError("Invalid type for comparison to PointInfo")


    def __ne__(self, other):
        return not self.__eq__(other)

    def _infostr(self, tab=0):
        lenself = len(self)
        tabstr = " "*tab
        basestr = ",\n"+tabstr
        if lenself > 0:
            entries = self.sortByIndex()
            if lenself > 8:
                return basestr.join([_pretty_print_label(i) for i in entries[0:3]]) + ",\n" +\
                       (tabstr + " .\n")*3 + tabstr +\
                       basestr.join([_pretty_print_label(i) for i in entries[-3:]])
            else:
                return basestr.join([_pretty_print_label(i) for i in entries])
        else:
            return "Empty"


    def __repr__(self):
        return self._infostr()

    __str__ = __repr__


def _pretty_print_label(d):
    """Internal utility to pretty print point label info."""
    s = " %s: "%repr(d[0])
    entry_keys = d[1].keys()
    ki = 0
    kimax = len(entry_keys)
    for k in entry_keys:
        keys = d[1][k].keys()
        if len(keys) == 0:
            s += "{%s: {}}"%k
        else:
            s += "{%s: {keys=%s}}"%(k,",".join(keys))
        if ki < kimax-1:
            s += ', '
        ki += 1
    return s

# ------------------------------------------------


def comparePointCoords(p1, p2, fussy=False):
    """Compare two Points, Pointsets, or dictionary of point data, coordinate-wise.
    If p1 or p2 are Pointsets, their independent variable values, if present, are
    *not* compared.

    fussy option causes point norm order and coordinate types to be
    checked too (requires both arguments to be Points or Pointsets)."""
    try:
        p1d = dict(p1)
        p1dk = p1d.keys()
        p2d = dict(p2)
        p2dk = p2d.keys()
    except:
        raise TypeError("Invalid Points, Pointsets, or dictionaries passed "
                        "to comparePointCoords")
    test1 = alltrue([ks[0]==ks[1] for ks in zip(p1dk, p2dk)])
    test2 = alltrue([vs[0]==vs[1] for vs in \
                 zip([p1d[k] for k in p1dk], [p2d[k] for k in p2dk])])
    if fussy:
        try:
            test3 = p1._normord == p2._normord
            test4 = compareNumTypes(p1.coordtype, p2.coordtype)
            return test1 and test2 and test3 and test4
        except AttributeError:
            raise TypeError("Invalid Points, Pointsets, or dictionaries passed "
                            "to comparePointCoords with fussy option")
    else:
        return test1 and test2


def isparameterized(p):
    return p._parameterized


def makeNonParameterized(p):
    if isinstance(p, Pointset) and p._isparameterized:
        return Pointset({'coordarray': copy(p.coordarray),
                         'coordnames': copy(p.coordnames),
                         'norm': p._normord,
                         'labels': copy(p.labels)})
    else:
        raise TypeError("Must provide a parameterized Pointset")


def pointsToPointset(pointlist, indepvarname='', indepvararray=None,
                     indepvartype=float64, norm=2):
    """Generate a Pointset from a list of Point objects (or a singleton Point).

    Include a name for the independent variable if constructing a
    parameterized pointset. The independent variable should be a
    coordinate of the Points passed, otherwise it can be passed as the
    optional third argument."""

    if not isinstance(indepvarname, str):
        raise TypeError("String expected for independent variable name")
    if isinstance(pointlist, Point):
        pointlist = [pointlist]
    coordnames = []
    ptype = ''
    paramd = indepvarname != ""
    if not paramd and indepvararray is not None:
        raise ValueError("Must supply independent variable name for "
                         "parameterized Pointset")
    if paramd and indepvararray is None:
        iv = []
    i = 0
    labels = {}
    for p in pointlist:
        assert isinstance(p, Point), \
               "pointlist argument must only contain Points"
        if coordnames == []:
            ptype = p.coordtype
            pdim = p.dimension
            coordnames = p.coordnames
            xcoordnames = copy(coordnames)
            if paramd and indepvararray is None:
                assert indepvarname in coordnames, \
                    "Independent variable name missing"
                del xcoordnames[xcoordnames.index(indepvarname)]
            dv = {}.fromkeys(xcoordnames)
            for c in xcoordnames:
                dv[c] = []
            if p.labels != {}:
                labels.update({0: p.labels})
                i += 1
        else:
            # coerce ints to float types if mixed
            if compareNumTypes(ptype, int32):
                if compareNumTypes(p.coordtype, float64):
                    ptype = float64
                elif compareNumTypes(p.coordtype, int32):
                    pass
                else:
                    raise TypeError("Type mismatch in points")
            elif compareNumTypes(ptype, float64):
                if not compareNumTypes(p.coordtype, (float64, int32)):
                    raise TypeError("Type mismatch in points")
            else:
                raise TypeError("Type mismatch in points")
            assert pdim == p.dimension, "Dimension mismatch in points"
            if remain(coordnames,p.coordnames) != []:
                raise ValueError("Coordinate name mismatch in points")
            if p.labels != {}:
                labels.update({i: p.labels})
                i += 1
        for c in xcoordnames: dv[c].append(p(c))
        if paramd and indepvararray is None:
            iv.append(p(indepvarname))
    # submit data as array to maintain coordname ordering present in Points
    dim = len(xcoordnames)
    ca = array([dv[c] for c in xcoordnames], ptype)
    argDict = {'coordarray': ca,
               'coordnames': xcoordnames,
               'coordtype': ptype,
               'labels': labels,
               'norm': norm
                 }
    if paramd:
        if indepvararray is None:
            indepvararray = array(iv, ptype)
        argDict.update({'indepvarname': indepvarname,
                         'indepvararray': indepvararray,
                         'indepvartype': indepvartype})
    return Pointset(argDict)


def arrayToPointset(a, vnames=None, ia=None, iname=""):
    """Convert an array to a non-parameterized Pointset. The inclusion of an
    optional independent variable array creates a parameterized Pointset.

    Coordinate (and independent variable) names are optional: the defaults are
    the array indices (and 't' for the independent variable)."""
    if rank(a) > 2:
        raise ValueError("Cannot convert arrays of rank > 2")
    if rank(a) == 0:
        raise ValueError("Cannot convert arrays of rank 0")
    if vnames is None:
        vnames = [str(i) for i in range(shape(a)[0])]
    else:
        if len(vnames) != shape(a)[0]:
            raise ValueError("Mismatch between number of coordinate names and"
                             " number of rows in array.\nCoordinates are "
                             "assumed to be the rows of the array")
    if ia is None:
        assert iname=="", ("Independent variable name must be none if no "
                           "independent variable array provided")
        return Pointset({'coordarray': a,
                     'coordnames': vnames})
    else:
        if iname == "":
            iname = "t"
        return Pointset({'coordarray': a,
                     'coordnames': vnames,
                     'indepvararray': ia,
                     'indepvarname': iname})

def exportPointset(thepointset, infodict, separator='   ',
                   precision=12, varvaldir='col',
                   ext='', append=False):
    """Export a pointset to a set of ASCII whitespace- (or
    user-defined character-) separated data files. Option to list each
    variable's data in rows ('across') or in columns ('down').
    Existing files of the same names will be overwritten, unless the
    'append' boolean option is set.

    NB. If the file extension argument 'ext' is present without a
    leading dot, one will be added.

    infodict should consist of: keys = filenames, values = tuples of
    pointset variable names to export.
    """
    assert varvaldir in ['col', 'row'], \
           "invalid variable value write direction"
    # in order to avoid import cycles, cannot explicitly check that
    # thepointset is of type Pointset, because Points.py imports this file
    # (utils.py), so check an attribute instead.
    try:
        thepointset.coordnames
    except AttributeError:
        raise TypeError("Must pass Pointset to this function: use "
                        "arrayToPointset first!")
    infodict_usedkeys = []
    for key, info in infodict.iteritems():
        if isinstance(info, str):
            infodict_usedkeys += [info]
        elif info == []:
            infodict[key] = copy.copy(thepointset.coordnames)
            infodict_usedkeys.extend(thepointset.coordnames)
        else:
            infodict_usedkeys += list(info)
    allnames = copy(thepointset.coordnames)
    if thepointset._parameterized:
        allnames.append(thepointset.indepvarname)
    remlist = remain(infodict_usedkeys, allnames+range(len(allnames)))
    if remlist != []:
        print "Coords not found in pointset:", remlist
        raise ValueError("invalid keys in infodict - some not present "
                         "in thepointset")
    assert isinstance(ext, str), "'ext' extension argument must be a string"
    if ext != '':
        if ext[0] != '.':
            ext = '.'+ext
    if append:
        assert varvaldir == 'col', ("append mode not supported for row"
                                     "format of data ordering")
        modestr = 'a'
    else:
        modestr = 'w'
    totlen = len(thepointset)
    if totlen == 0:
        raise ValueError("Pointset is empty")
    for fname, tup in infodict.iteritems():
        try:
            f = open(fname+ext, modestr)
        except IOError:
            print "There was a problem opening file "+fname+ext
            raise
        try:
            if isinstance(tup, str):
                try:
                    varray = thepointset[tup]
                except TypeError:
                    raise ValueError("Invalid specification of coordinates")
            elif isinstance(tup, int):
                try:
                    varray = thepointset[:,tup].toarray()
                except TypeError:
                    raise ValueError("Invalid specification of coordinates")
            elif isinstance(tup, (list, tuple)):
                if alltrue([isinstance(ti,str) for ti in tup]):
                    thetup=list(tup)
                    if thepointset.indepvarname in tup:
                        tix = thetup.index(thepointset.indepvarname)
                        thetup.remove(thepointset.indepvarname)
                    try:
                        vlist = thepointset[thetup].toarray().tolist()
                    except TypeError:
                        raise ValueError("Invalid specification of coordinates")
                    if len(thetup)==1:
                        vlist = [vlist]
                    if thepointset.indepvarname in tup:
                        vlist.insert(tix, thepointset.indepvararray.tolist())
                    varray = array(vlist)
                elif alltrue([isinstance(ti,_int_types) for ti in tup]):
                    try:
                        varray = thepointset[:,tup].toarray()
                    except TypeError:
                        raise ValueError("Invalid specification of coordinates")
                else:
                    raise ValueError("Invalid specification of coordinates")
            else:
                f.close()
                raise TypeError("infodict values must be singletons or "
                                "tuples/lists of strings or integers")
        except IOError:
            f.close()
            print "Problem writing to file"+fname+ext
            raise
        except KeyError:
            f.close()
            raise KeyError("Keys in infodict not found in pointset")
        if isinstance(precision, int):
            assert precision > 0
            ps = str(precision)
        else:
            raise TypeError("precision must be a positive integer")
        if varvaldir == 'row':
            savetxt(f, varray, '%.'+ps+'f', separator)
        else:
            savetxt(f, transpose(varray), '%.'+ps+'f', separator)
        f.close()


def importPointset(xFileName, t=None, indices=None, sep=" ",
                   preamblelines=0):
    """Import ASCII format files containing data points.
    If the first row contains string names then the output
    will be a pointset, otherwise a numeric array.

    A dictionary is returned, with keys 'vararray' will point to the
    data. The 't' argument can specify one of several things:

    string: filename to read single-column of time values (same length as
            xFileName)
    sequence type: time values (same length as xFileName)
    integer: column in xFileName to treat as time data

    If used, this leads to and an additional key in the return
    dictionary where 't' points to the independent variable array.

    Specific columns can be selected for the variable data array by
    specifying a list of column indices in argument 'indices'.

    The separator used in the ASCII file can be specified by argument
    'sep' (defaults to single whitespace character).

    preamblelines (positive integer) specifies how many lines to skip before
    starting to read data (in case of preceding text) -- default 0.
    """

    if indices is None:
        indices = []
    xFile = open(xFileName, 'r')
    xFileStrList = xFile.readlines()
    filelen = len(xFileStrList)-preamblelines
    if filelen == 1 and '\r' in xFileStrList[0]:
        # fix problem when no newlines picked up, only '\r'
        xFileStrList = xFileStrList[0].split('\r')
        filelen = len(xFileStrList)
    if filelen <= 1:
        raise ValueError("Only 1 data point found in variables datafile")
    x_dummy_all = xFileStrList[preamblelines].rstrip("\n")
    x_dummy_vallist = filter(lambda s: s != '', x_dummy_all.split(sep))
    if t is None:
        get_t = 0
    elif isinstance(t, str):
        tFileName = t
        tFile = open(tFileName, 'r')
        tFileStrList = tFile.readlines()
        if len(tFileStrList)-preamblelines != filelen:
            raise ValueError("Length of data and time files must be equal"
                           " -- are there any blank lines in the files?")
        get_t = 1
    elif isinstance(t, _seq_types):
        if len(t) != filelen:
            raise ValueError("Length of data file and t array must be "
                       "equal -- are there any blank lines in the files?")
        tVals = t
        get_t = 0
    elif isinstance(t, _int_types):
        # t represents column index to find time data in data file
        if t >= len(x_dummy_vallist) or t < 0:
            raise ValueError("t index out of range")
        get_t = 2
    if indices == []:
        if get_t == 2:
            dim = len(x_dummy_vallist)-1
            indices = remain(range(0,dim+1),[t])
        else:
            dim = len(x_dummy_vallist)
            indices = range(0,dim)
    else:
        dim = len(indices)
        if get_t == 2:
            if t in indices:
                raise ValueError("You specified column "+str(t)+" as time "
                    "data, but you have specified it as a data column in "
                    "indices argument")
    # try to find variable names. if successful, start at row 1
    start = preamblelines
    # replace unnecessary quote marks in strings
    test_line = [n.strip('"').strip("'") for n in \
            xFileStrList[preamblelines].lstrip(sep).lstrip(" ").rstrip("\n").rstrip("\r").split(sep)]
    def is_float(vstr):
        try:
            val = float(vstr)
        except ValueError:
            return False
        else:
            return True
    if alltrue([not is_float(n) for n in test_line]):
        # success
        start += 1
        # replace any internal spaces with underscores, remove dots
        test_line = [n.replace(" ", "_").replace(".","") for n in test_line]
        if get_t == 2:
            t_name = test_line[t]
            varnames = test_line[0:t]+test_line[t+1:]
        else:
            if get_t == 1:
                # try first line of t file
                t_test = tFileStrList[0].lstrip(" ").rstrip("\n").rstrip("\r").replace(".","").replace(" ","_").strip('"').strip("'")
                if is_float(t_test):
                    # already checked that file lengths were the same
                    raise ValueError("First line of t file shouldn't be a number")
                else:
                    t_name = t_test
            else:
                t_name = 't'
            varnames = test_line
    else:
        t_name = 't'
        varnames = None
    tVals = zeros(filelen-start, float)
    xVals = zeros([filelen-start, dim], float)
    # read rest of file
    for i in xrange(filelen-start):
        vLine = xFileStrList[i+start].rstrip("\n")
        if vLine == '':
            continue
        vLineVals = filter(lambda s: s != '', vLine.split(sep))
        if get_t == 1:
            # Additional left strip of space char in case sep is different
            tLine = tFileStrList[i+start].rstrip("\n").lstrip(sep).lstrip(" ")
            if len(tLine.split(sep)) != 1:
                raise ValueError("Only one t value expected per line of"
                                   " datafile")
            if tLine == '':
                continue
            tVals[i] = float(tLine)
        elif get_t == 2:
            tVals[i] = float(vLineVals[t])
        try:
            xLineVals = [vLineVals[ix] for ix in indices]
        except IndexError:
            print "Valid indices were: 0 -", len(vLineVals)-1
            raise
        if len(xLineVals) != dim:
            raise ValueError("Exactly "+str(dim)+" values expected per "
                               "line of datafile")
        xVals[i] = array([float(xstr) for xstr in xLineVals], float)
    xFile.close()
    if get_t == 1:
        tFile.close()
    if get_t == 0:
        if varnames is None:
            return xVals
        else:
            # non-parameterized pointset
            return Pointset(dict(zip(varnames, xVals)))
    else:
        if varnames is None:
            return {t_name: tVals, 'vararray': xVals.T}
        else:
            return Pointset(indepvardict={t_name: tVals},
                            coorddict=dict(zip(varnames,xVals.T)))


def padPointset(pts, pinterval, value_dict, eps=None):
    """Pad a pointset pts with values from value_dict over the interval given
    by pinterval. For each side of the interval outside of the current independent
    variable domain of pts, two new points are added, one at the outer limit
    of the interval, and one a distance eps (default the abseps setting of pts)
    from the existing closest point in pts.
    """
    tlo, thi = pinterval
    ts = pts.indepvararray
    all_dict = value_dict.copy()
    assert remain(value_dict.keys(), pts.coordnames) == []
    if eps is None:
        eps = pts._abseps
    if tlo < ts[0]:
        all_dict['t'] = tlo
        pts.insert(Point(coorddict=all_dict,
                         labels='pad'))
        all_dict['t'] = ts[0]-eps
        pts.insert(Point(coorddict=all_dict,
                         labels='pad'))
    if thi > ts[-1]:
        all_dict['t'] = ts[-1]+eps
        pts.insert(Point(coorddict=all_dict,
                         labels='pad'))
        all_dict['t'] = thi
        pts.insert(Point(coorddict=all_dict,
                         labels='pad'))
    return pts

# -----------------------------


def test_point():
    print "\n****** Point class test ******\n"
    print "x uses Python float type:"
    xstr = """x = Point({'coorddict': {'x0': [1.123456789], 'x1': [-0.4],
                   'x2': [4000]},
               'coordtype': float})"""
    print xstr
    exec(xstr)
    # float is equivalent to float64
    print "x => ", repr(x)
    print "x.toarray() = ", x.toarray()
    print "\nprint x => ", x
    print "x.dimension => ", x.dimension, ", x.coordnames => ", x.coordnames
    print "x.coordtype => ", x.coordtype
    print "x.coordtype => ", x.coordtype
    print "x('x1') = ", x('x1')
    print "x(['x1','x0']) = ", x(['x1','x0'])
    print "x([0,1]) = ", x([0,1])
    print "\nChanging x entries is done by x[index] = value:"
    print "x[1] = -0.45"
    x[1] = -0.45
    print "\nThe index can also be a name, a list of names, or even a dictionary:"
    print "x[['x0', 'x1']] = [4.11103, -0.56])"
    x[['x0', 'x1']] = [4.11103, -0.56]
    print "\ny is a 1D point (with integer type):"
    # can also specify as array([4])
    ystr = """y = Point({'y': 4})"""
    print ystr
    exec(ystr)
    print "print y => ", y
    print "y(0) = ", y(0)
    print "type(y(0)) => ", type(y(0))
    print "y([0]) = ", y([0])
    print "y.toarray() = ", y.toarray()
    assert comparePointCoords(x,(x+0)*1,fussy=True)
    # pass x back
    return x


def test_pointset():
    print "\n\n****** Pointset test ******\n"
    print "v is a 'singleton' pointset, to make sure this doesn't break the interface"
    vstr = """v = Pointset({'coorddict': {'x0': 0.2, 'x1': -1.2},
                 'indepvardict': {'t': 0.01},
                 'coordtype': float64,
                 'indepvartype': float64
                  })"""
    print vstr
    exec(vstr)
    print "print v =>", v
    print "\nprint v(0.01) => ", v(0.01)
    print "and v(0.01) is a Point object\n"
    print "print v(0.01, 0) => ", v(0.01, 0)
    print "and v(0.01, 0) is a float\n"
    print "print v(0.01, 'x0') => ", v(0.01, 'x0')

    print "\nk tests deprecated syntax for single-point pointset"
    kstr = """k = Pointset({'coordarray': array(0.1),
                  'coordnames': 'k0',
                  'indepvarname': 't',
                  'indepvararray': array(0.0)})"""
    print kstr
    exec(kstr)
    assert k.dimension == 1
    print "print k.toarray() => ", k.toarray()
    print "print k['t'] => ", k['t']
    print "print k(0.0) => ", k(0.0)
    print "print k => ", k

    print "\nu tests non-parameterized pointset"
    ustr = """u = Pointset({'coordarray': array([10., 20., 30., 40.])})"""
    exec(ustr)
    print ustr
    print "u.toarray() => ", u.toarray()
    print "isparameterized(u) => ", isparameterized(u)
    print "print u => ", u

    print "\nw tests alternative declaration syntax, and other forms of calling"
    wstr = """wp = Pointset({'coordarray': array([[4.456, 2.34634, 7.3431, 5.443],
                                  [-10.0336, -5.2235, -3.23221, -0.01],
                                  [3e5, 3.1e5, 3.3e5, 2.8e5]], float64),
                  'coordnames': ['x0', 'x1', 'x2'],
                  'indepvarname': 't',
                  'indepvararray': array([0.0, 1.0, 2.0, 3.0], float64)})"""
    print wstr
    exec(wstr)
    assert type(wp.coordarray)==type(array([1,2],float64))
    print "wp.dimension => ", wp.dimension
    print "print wp(0.0) => ", wp(0.0)
    print "type(wp(0.0)) => ", type(wp(0.0))
    print "print wp(1.0)(0) => ", wp(1.0)(0)
    print "print wp(2.0, 'x1') => ", wp(2.0, 'x1')
    print "\nprint wp(2.0, ['x2', 'x1']) => ", wp(2.0, ['x2', 'x1'])
    print "type(wp(2.0, ['x1', 'x2'])) => ", type(wp(2.0, ['x1', 'x2']))
    print "print wp[['x1','x0']] => ", wp[['x1','x0']]
    print "\nwp.info(1) =>", wp.info(1)
    print "wp(1.0).info(1) =>", wp(1.0).info(1)
    print "wp['t'] => ", wp['t']
    print "\nCall several 't' values at once (explicit values only -- no ellipses):"
    print "wp([1., 2.]) => ", wp([1., 2.])
    print "\nExtract a coordinate (only by name) as a regular array:"
    w_x0 = wp['x0']
    print "w_x0 = wp['x0']  => ", w_x0

    print "\nExtract a point of w as a regular array:"
    w_at_1 = wp(1.).toarray()
    print "w_at_1 = wp(1.).toarray()  => ", w_at_1

    print "\nMany forms to access individual values or sub-arrays:"
    print "wp(1., 'x1') => ", wp(1., 'x1')
    print "wp(1.)('x1') => ", wp(1.)('x1')
    print "wp(1., 1)) => ", wp(1., 1)
    print "wp([1.,3.], 1) => ", wp([1.,3.], 1)
    print "wp([1.,3.])('x1') => ", wp([1.,3.])['x1']
    print "wp(1.)([0,1]) => ", wp(1.)([0,1])
    print "but ... wp([1.])(1., [0,1]) => ", wp([1.])(1., [0,1])
    print "... because wp([1.]) is a Pointset and wp(1.) is a Point"
    print "This is why wp(1.).toarray() shows a different array shape to wp([1.]).toarray():"
    print "wp(1.).toarray().shape => ", wp(1.).toarray().shape
    print "wp([1.]).toarray().shape => ", wp([1.]).toarray().shape

    print "\nChange a point in w using wp[indepvar_value] = point:"
    print "Old value at t=1.0:  wp(1.0) =>", wp(1.0)
    print "wp[1] = x"
    wp[1] = x
    print "w has now been updated for the meshpoint at t=1.0  =>"
    print "New value at t=1.0:  wp(1.0) => ", wp(1.0)
    assert type(wp.coordarray)==type(array([1,2],float64))

    print "\nWe can test equality between arrays, as usual:"
    print "w_at_1 != wp(1.).toarray() => ", w_at_1 != wp(1.).toarray()
    print "We can also compare with a Pointset object:"
    print "wp(1.) != w_at_1 => ", wp(1.) != w_at_1
    print "But we can't put an array on the left-hand side if a Point or " \
          "Pointset is on the right."

    print "\nTo demonstrate appending a Point and Pointset to another Pointset:"
    vw = Pointset({'coorddict': {'x0': [0.1, 0.15], 'x1': [100., 102], 'x2': [0.2, 0.1]},
                 'indepvardict': {'t': [4.5, 5.0]},
                 'coordtype': float64,
                 'indepvartype': float64,
                 'labels': {1: 'c'}
                  })
    print "vw.labels -->", vw.labels
    print "wp.append(vw)"
    wp.append(vw)
    print "wp.labels -->", wp.labels
    assert type(wp.coordarray)==type(array([1,2],float64))
    wp.append(Point({'coorddict': {'t': 6.5, 'x0': 2, 'x1': -300, 'x2': -0.9997}}))
    assert type(wp.coordarray)==type(array([1,2],float64))
    print "\nwp.toarray() -->\n", wp.toarray()
    print "\nwp(4.5) -->\n", wp(4.5)
    print "\nwp[[3,6]] -->", wp[[3,6]]
    print "\nwp[3:5] -->", wp[3:5]
    print "\nwp[2:] -->", wp[2:]
    try:
        # index out of range
        wp[10:]
    except ValueError:
        pass
    print "\nwp[wp.findIndex(4.5)] -->\n", wp[wp.findIndex(4.5)]
    print "\nwp.labels -->", wp.labels
    print "\nLabels test:"
    wp.labels[3] = ('a', {'bif':'SN'})
    print "wp.labels[3] -->", wp.labels[3]
    wp_part = wp[3:5]
    print "wp_part.labels -->", wp_part.labels
    assert wp_part.labels[0] == wp.labels[3]
    wpt = wp(3.)
    assert wpt.labels == {'a': {'bif':'SN'}}
    wp_ins = Pointset({'coorddict': {'x0': [-2.1, -4., -5., -4.5], 'x1': [50., 51., 52., 54.], 'x2': [0.01, 0.02, 0.4, 0.9]},
                 'indepvardict': {'t': [1.5, 5.2, 9., 10.]},
                 'coordtype': float64,
                 'indepvartype': float64,
                 'labels': {2: 'b', 3: {'a': {'bif':'H'}}}
                  })
    print "\nwp_ins object created to insert into wp:"
    print wp_ins
    wp.insert(wp_ins)
    print "\nwp.insert(wp_ins) -->\n", wp

    print "\nTo demonstrate building a Pointset from a list of Point objects:"
    codestr = """pointlist = []
for t in wp['t']:
    pointlist.append(wp(t))
w_reconstructed = pointsToPointset(pointlist, 't', wp['t'])"""
    print codestr
    exec(codestr)
    print "\nAnd to demonstrate that this yields an identical object:"
    print "w_reconstructed == w  => ", w_reconstructed == wp

    try:
        w_double = w_reconstructed.append(w_reconstructed)
        raise RuntimeError("Internal error with Pointset class!")
    except ValueError:
        print "(ensure that any independent variable values to append are well-ordered)"

    print "\nTest of non-parameterized use of pointsToPointset:"
    wnp = pointsToPointset(pointlist)
    print "(Adding two additional labels to wnp)"
    wnp.labels[0]=('b', {})
    wnp.addlabel(4, 'c', {'bif': 'H'})  # preferred syntax
    print wnp
    print "\nwnp[:] -->\n", wnp[:]
    print "-- OK!"

    print "\nCan iterate over points and pointsets:"
    print "for p in wnp.bylabel('a'):\n  print p\n"
    for p in wnp.bylabel('a'):
        print p

    # pass some of the objects back
    return wp, wnp, wpt, wp_part


def test_pointset_labels(wp):
    #wp = wp.copy()
    wp2 = Pointset({'coorddict': {'x0': [-4.5, 2, 3], 'x1': [54, 62, 64], 'x2': [0.9, 0.8, 0.2]},
                 'indepvardict': {'t': [10, 11, 12]},
                 'coordtype': float64,
                 'indepvartype': float64,
                 'labels': {0: {'a_different': {'bif':'H'}},
                            2: 'd'}
                  })
    wp.append(wp2, skipMatchingIndepvar=True)
    assert len(wp) == 13
    assert wp.bylabel('b')['t'][0] == 9.0
    assert all(wp.bylabel('a')['t'] == array([3., 10.]))
    assert wp.bylabel('d')['t'][0] == 12.0
    assert all(wp.bylabel('a_different')['t'] == array([10.]))
    z = wp[-5:]
    assert z.labels.getIndices() == [1,2,4]

# -----------------------------

if __name__ == '__main__':
    x = test_point()
    wp, wnp, wpt, wp_part = test_pointset()
    test_pointset_labels(wp)
    print "\n"
    print "x (point) and wp, wnp (param'd and non-param'd pointsets) are available in the global namespace,", \
          "to play with interactively now that this script has run."
