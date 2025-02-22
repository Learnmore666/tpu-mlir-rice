# ==============================================================================
#
# Copyright (C) 2022 Sophgo Technologies Inc.  All rights reserved.
#
# TPU-MLIR is licensed under the 2-Clause BSD License except for the
# third-party components.
#
# ==============================================================================
from enum import Enum
import numpy as np
import functools

try:
    from . import op_support
    from . import disassembler
except:
    import op_support
    import disassembler


class Device(Enum):
    BM1684X = "BM1684X"
    BM1684 = "BM1684"


class Context:
    __slots__ = "opdef", "opparam", "device"

    def __init__(self, device: Device):
        self.device = Device(device)
        if self.device == Device.BM1684X:
            from . import opdef_1684x
            from . import opparam_1684x

            self.opdef = opdef_1684x
            self.opparam = opparam_1684x
        elif self.device == Device.BM1684:
            from . import opdef_1684
            from . import opparam_1684

            self.opdef = opdef_1684
            self.opparam = opparam_1684

        else:
            raise ValueError(f"Unknown device: {device}")

    def __bind_resource(self, cmodel):
        # bind compute
        for _, v in self.opdef.tiu_cls.items():
            for op in v:
                setattr(op, "compute", lambda c: cmodel.tiu_compute(c.cmd))

        for _, v in self.opdef.dma_cls.items():
            for op in v:
                setattr(op, "compute", lambda c: cmodel.dma_compute(c.cmd))

        # bind memory operation
        memory = self.opparam.Memory(cmodel.LMEM, cmodel.DDR)

        @property
        def data(self):
            return memory.get_data(self)

        @data.setter
        def data(self, np_data):
            memory.set_data(self, np_data)

        setattr(self.MemRef, "data", data)

    def get_runner(self, memory_size):
        try:
            from . import cmodel
        except:
            import cmodel

        if self.device == Device.BM1684X:
            _cmodel = cmodel.BM1684X(memory_size)
        elif self.device == Device.BM1684:
            _cmodel = cmodel.BM1684(memory_size)
        else:
            raise ValueError(f"device: {self.device} is not supported.")

        self.__bind_resource(_cmodel)
        return _cmodel

    @property
    def memmap(self):
        return self.opparam.memmap

    @property
    def MemRef(self):
        return self.opparam.MemRef

    @property
    @functools.lru_cache()
    def decoder(self):
        return disassembler.Decoder(self)

    def BModel2MLIR(self, bmodel):
        return disassembler.BModel2MLIR(bmodel, self.decoder)

    def tensor2memref(self, tensor):
        assert tensor.pad_h == 0, "Not supports pad_h."
        dtype = op_support.DType(tensor.dtype)
        if tensor.st_mode in (1, 2):  # 2N/4N
            assert self.device == Device.BM1684
            # The type should be declared explicitly.
            layout = op_support.Layout.continuous_XN
            xn = 4 // dtype.itemsize
            stride = op_support.get_continuous_stride(tensor.shape[0]) * xn
        else:
            stride = op_support.get_continuous_stride(tensor.shape[0])
            layout = None  # global is continuous
        return self.MemRef(
            tensor.device_addr,
            tensor.shape[0],
            dtype,
            stride=stride,
            layout=layout,
        )
