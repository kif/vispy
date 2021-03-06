# -*- coding: utf-8 -*-
# Copyright (c) 2014, Vispy Development Team. All Rights Reserved.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
# Author: Jérôme Kieffer
# -----------------------------------------------------------------------------
""" Definition of OpenCL interaction using PyOpenCL

This module defines a class OpenCL which provides an method to retrieve an
OpenCL context shared with OpenGL.

A couple of classes are providing a get_ocl method to retrieve the OpenCL
view on OpenGL textures or buffers.

All exposed classes from gloo.buffer and gloo.texture are mixed using dual-
inheritance to offer views.
"""

from __future__ import division, print_function
import sys
from ..gloo import gl, texture, buffer
from ..util import logger
from threading import Semaphore

try:
    import pyopencl
    import pyopencl.array
    from pyopencl.tools import get_gl_sharing_context_properties
except ImportError:
    logger.warning("Unable to import PyOpenCL. "
                   "Please install it from:"
                   " http://pypi.python.org/pypi/pyopencl")
    pyopencl = None

if pyopencl and not pyopencl.have_gl():
    logger.warning("PyOpenCL is installed but was compiled"
                   " without OpenGL support.")
    pyopencl = None


def _make_context(platform_id=None, device_id=None):
    """
    Actually creates a context and return its ids'

    Parameters
    ----------
    platform_id : platform number
        int
    device_id : device number in the platform
        int

    """
    if not pyopencl:
        raise RuntimeError("PyOpenCL not installed on the system !")
    properties = get_gl_sharing_context_properties()
    enum_plat = pyopencl.context_properties.PLATFORM
    ids = None
    if (platform_id is not None) and (device_id is not None):
        platform = pyopencl.get_platforms()[platform_id]
        device = platform.get_devices()[device_id]
        try:
            ctx = pyopencl.Context(devices=[device],
                                   properties=[(enum_plat, platform)]
                                   + properties)
            ids = (platform_id, device_id)
        except:
            ctx = None

    elif sys.platform == "darwin":
        ctx = pyopencl.Context(properties=properties,
                               devices=[])
        for platform_id, platform in enumerate(pyopencl.get_platforms()):
            for device_id, device in enumerate(platform.get_device()):
                if ctx.devices[0] == device:
                    ids = (platform_id, device_id)
    else:
        # Some OSs prefer clCreateContextFromType, some prefer
        # clCreateContext. Try both and loop.
        for platform_id, platform in enumerate(pyopencl.get_platforms()):
            try:
                ctx = pyopencl.Context(properties=properties +
                                       [(enum_plat, platform)])
                device = ctx.devices[0]
                if device.type != pyopencl.device_type.GPU:
                    # Wrongly selected non GPU device
                    ctx = None
                    raise
            except:
                for device_id, device in enumerate(platform.get_devices()):
                    if device.type != pyopencl.device_type.GPU:
                        continue
                    try:
                        ctx = pyopencl.Context(devices=[device],
                                               properties=properties +
                                               [(enum_plat, platform)])
                    except:
                        ctx = None
                    else:
                        ids = (platform_id, device_id)
                        break
            else:
                for device_id, device in enumerate(platform.get_devices()):
                    if ctx.devices[0] == device:
                        ids = (platform_id, device_id)
                        break
                break
            if ctx:
                break
    return ctx, ids


class OpenCL(object):

    """
    Provides a class method to retrieve an
    OpenCL context shared with OpenGL.
    """
    _ids = None
    _context = None
    _sem = Semaphore()

    @classmethod
    def get_context(cls, platform_id=None, device_id=None):
        """
        Retrieves the OpenCL context

        Parameters
        ----------
        platform_id : platform number
            int
        device_id : device number in the platform
            int
        """
        if not pyopencl:
            raise RuntimeError("OpenCL un-useable")
        ctx = None
        ids = (platform_id, device_id)
        if ids == cls._ids:
            ctx = cls._context
        elif (platform_id is None) and (device_id is None) and cls._context:
            ctx = cls._context
        elif (cls._context is None) or (ids != cls._ids):
            with cls._sem:
                if (cls._context is None) or (ids != cls._ids):
                    cls._context, cls._ids = _make_context(platform_id,
                                                           device_id)
                    ctx = cls._context
                    ids = cls._ids
        if ctx is None:
            raise RuntimeError("Unable to find suitable OpenCL platform "
                               "to share data with OpenGL")
        return ctx


class TextureOpenCL(OpenCL):

    """
    Mixing class to offer OpenCL view on the texture
    """

    def get_ocl(self, ctx=None):
        """
        Retrieves an OpenCL view on the texture.

        To use it you need to grab it using:
        pyopencl.enqueue_acquire_gl_objects(queue, [ocl_tex])

        Parameters
        ----------
        ctx: OpenCL Context
            If None is provided, generate/reuse an existing one
        """
        if not pyopencl:
            raise RuntimeError("OpenCL un-useable")

        if self._handle == 0:
            self.activate()

        if ctx is None:
            ctx = self.get_context()

#       Currently only ndim=2 looks possible:
        ndim = 2
        ocl_img = pyopencl.GLTexture(ctx, pyopencl.mem_flags.READ_WRITE,
                                     self._target, 0, int(self.handle), ndim)
        return ocl_img


class Texture1D(texture.Texture1D, TextureOpenCL):

    """ Representation of a 2D texture with OpenCL exchange capabilities.
    """

    def __init__(self, *args, **kwargs):
        texture.Texture1D.__init__(self, *args, **kwargs)


class Texture2D(texture.Texture2D, TextureOpenCL):

    """ Representation of a 2D texture with OpenCL exchange capabilities.
    """

    def __init__(self, *args, **kwargs):
        texture.Texture2D.__init__(self, *args, **kwargs)


class BufferOpenCL(OpenCL):

    """
    Mixing class to offer OpenCL view on the buffer
    """

    def get_ocl(self, ctx=None):
        """
        Retrieves an OpenCL view on the Buffer.

        To use it you need to grab it using:
        pyopencl.enqueue_acquire_gl_objects(queue, [ocl_buf])

        Parameters
        ----------
        ctx : OpenCL Context
            If None is provided, generate/reuse an existing one
        """
        if not pyopencl:
            raise RuntimeError("OpenCL un-useable")

        if self._handle == 0:
            self.activate()

        if ctx is None:
            ctx = self.get_context()

        cl_buf = pyopencl.GLBuffer(ctx, pyopencl.mem_flags.READ_WRITE,
                                   int(self.handle))
        return cl_buf


class VertexBuffer(buffer.VertexBuffer, BufferOpenCL):

    """ The VertexBuffer represents any kind of vertex data, and can also
    represent an array-of-structures approach.

    The shape of the given data is interpreted in the following way:
    If a normal array of one dimension is given, the vector-size (vsize)
    is considered 1. Otherwise, data.shape[-1] is considered the vsize,
    and the other dimensions are "collapsed" to get the vertex count.
    If the data is a structured array, the number of elements in each
    item is used as the vector-size (vsize).

    Parameters
    ----------
    data : ndarray or dtype
        Specify the data, or the type of the data. The dtype can also
        be something that evaluates to a dtype, such as a 'uint32' or
        np.uint8. If a structured array or dtype is given, and there
        are more than 1 elements in the structure, this buffer is a
        "structured" buffer. The corresponding items can be obtained
        by indexing this buffer using their name. In most cases
        one can use program.set_vars(structured_buffer) to map the
        item names to their GLSL attribute names automatically.
    client : bool
        Should be given as a keyword argument. If True, a
        ClientVertexBuffer is used instead, which is a lightweight
        wrapper class for storing vertex data in CPU memory.

    Example
    -------
    dtype = np.dtype( [ ('position', np.float32, 3),
                        ('texcoord', np.float32, 2),
                        ('color',    np.float32, 4) ] )
    data = np.zeros(100, dtype=dtype)

    program = Program(...)

    program.set_vars(VertexBuffer(data))
    """

    def __init__(self, *args, **kwargs):
        buffer.VertexBuffer.__init__(self, *args, **kwargs)
