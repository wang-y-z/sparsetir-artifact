from typing import Any
from transformers import AutoTokenizer, AutoModelForQuestionAnswering
from transformers import BertModel
from scipy import sparse as sp
import numpy as np
import torch as th
import pandas as pd
import argparse
import dgl
import tvm
from tvm.sparse.format import condense
import tvm.testing
import tvm.tir as tir
from tvm.script import tir as T
from tvm.sparse import lower_sparse_buffer, lower_sparse_iter
import torch.utils.benchmark as benchmark


@T.prim_func
def wmma_m16n16k16_sync_desc(a_frag: T.handle, b_frag: T.handle,
                             c_frag: T.handle) -> None:
    A_frag = T.match_buffer(a_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=1,
                            scope="wmma.matrix_a")
    B_frag = T.match_buffer(b_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=1,
                            scope="wmma.matrix_b")
    C_frag = T.match_buffer(c_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=1,
                            scope="wmma.accumulator")

    with T.block("root"):
        for i, k, j in T.grid(16, 16, 16):
            with T.block("update"):
                vii, vkk, vjj = T.axis.remap("SRS", [i, k, j])
                T.block_attr({"sparse": True})
                C_frag[vii,
                       vjj] = C_frag[vii,
                                     vjj] + A_frag[vii, vkk] * B_frag[vkk, vjj]


@T.prim_func
def wmma_m16n16k16_sync_impl(a_frag: T.handle, b_frag: T.handle,
                             c_frag: T.handle) -> None:
    A_frag = T.match_buffer(a_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_a")
    B_frag = T.match_buffer(b_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_b")
    C_frag = T.match_buffer(c_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")

    with T.block("root"):
        T.reads([
            C_frag[0:16, 0:16],
            A_frag[0:16, 0:16],
            B_frag[0:16, 0:16],
        ])
        T.writes(C_frag[0:16, 0:16])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_mma_sync(
                    C_frag.data,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 16),
                    A_frag.data,
                    A_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(A_frag.elem_offset, 256), 16),
                    B_frag.data,
                    B_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(B_frag.elem_offset, 256), 16),
                    C_frag.data,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 16),
                    dtype="handle",
                ))


@T.prim_func
def wmma_m8n32k16_sync_desc(a_frag: T.handle, b_frag: T.handle,
                            c_frag: T.handle) -> None:
    A_frag = T.match_buffer(a_frag, (8, 16),
                            "float16",
                            align=128,
                            offset_factor=1,
                            scope="wmma.matrix_a")
    B_frag = T.match_buffer(b_frag, (16, 32),
                            "float16",
                            align=128,
                            offset_factor=1,
                            scope="wmma.matrix_b")
    C_frag = T.match_buffer(c_frag, (8, 32),
                            "float16",
                            align=128,
                            offset_factor=1,
                            scope="wmma.accumulator")

    with T.block("root"):
        for i, k, j in T.grid(8, 16, 32):
            with T.block("update"):
                vii, vkk, vjj = T.axis.remap("SRS", [i, k, j])
                T.block_attr({"sparse": True})
                C_frag[vii,
                       vjj] = C_frag[vii,
                                     vjj] + A_frag[vii, vkk] * B_frag[vkk, vjj]


@T.prim_func
def wmma_m8n32k16_sync_impl(a_frag: T.handle, b_frag: T.handle,
                            c_frag: T.handle) -> None:
    A_frag = T.match_buffer(a_frag, (8, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_a")
    B_frag = T.match_buffer(b_frag, (16, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_b")
    C_frag = T.match_buffer(c_frag, (8, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")

    with T.block("root"):
        T.reads([
            C_frag[0:8, 0:32],
            A_frag[0:8, 0:16],
            B_frag[0:16, 0:32],
        ])
        T.writes(C_frag[0:8, 0:32])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_mma_sync(
                    C_frag.data,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 32),
                    A_frag.data,
                    A_frag.elem_offset // 128 +
                    T.floordiv(T.floormod(A_frag.elem_offset, 128), 16),
                    B_frag.data,
                    B_frag.elem_offset // 512 +
                    T.floordiv(T.floormod(B_frag.elem_offset, 512), 32),
                    C_frag.data,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 32),
                    dtype="handle",
                ))


@T.prim_func
def wmma_m16n16k16_load_a_desc(a: T.handle, a_frag: T.handle) -> None:
    A = T.match_buffer(a, (16, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global")
    A_frag = T.match_buffer(a_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_a")

    with T.block("root"):
        T.reads(A[0:16, 0:16])
        T.writes(A_frag[0:16, 0:16])
        for i, j in T.grid(16, 16):
            with T.block("load"):
                vii, vjj = T.axis.remap("SS", [i, j])
                A_frag[vii, vjj] = A[vii, vjj]


@T.prim_func
def wmma_m16n16k16_load_a_impl(a: T.handle, a_frag: T.handle) -> None:
    s0 = T.var("int32")
    s1 = T.var("int32")
    A = T.match_buffer(a, (16, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global",
                       strides=[s0, s1])
    A_frag = T.match_buffer(a_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_a")

    with T.block("root"):
        T.reads(A[0:16, 0:16])
        T.writes(A_frag[0:16, 0:16])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_load_matrix_sync(
                    A_frag.data,
                    16,
                    16,
                    16,
                    A_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(A_frag.elem_offset, 256), 16),
                    A.access_ptr("r"),
                    A.strides[0],
                    "row_major",
                    dtype="handle",
                ))


@T.prim_func
def wmma_m8n32k16_load_a_desc(a: T.handle, a_frag: T.handle) -> None:
    A = T.match_buffer(a, (8, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global")
    A_frag = T.match_buffer(a_frag, (8, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_a")

    with T.block("root"):
        T.reads(A[0:8, 0:16])
        T.writes(A_frag[0:8, 0:16])
        for i, j in T.grid(8, 16):
            with T.block("load"):
                vii, vjj = T.axis.remap("SS", [i, j])
                A_frag[vii, vjj] = A[vii, vjj]


@T.prim_func
def wmma_m8n32k16_load_a_impl(a: T.handle, a_frag: T.handle) -> None:
    s0 = T.var("int32")
    s1 = T.var("int32")
    A = T.match_buffer(a, (8, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global",
                       strides=[s0, s1])
    A_frag = T.match_buffer(a_frag, (8, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_a")

    with T.block("root"):
        T.reads(A[0:8, 0:16])
        T.writes(A_frag[0:8, 0:16])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_load_matrix_sync(
                    A_frag.data,
                    8,
                    32,
                    16,
                    A_frag.elem_offset // 128 +
                    T.floordiv(T.floormod(A_frag.elem_offset, 128), 16),
                    A.access_ptr("r"),
                    A.strides[0],
                    "row_major",
                    dtype="handle",
                ))


@T.prim_func
def wmma_m16n16k16_load_b_desc(b: T.handle, b_frag: T.handle) -> None:
    B = T.match_buffer(b, (16, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="shared")
    B_frag = T.match_buffer(b_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_b")
    with T.block("root"):
        for i, j in T.grid(16, 16):
            with T.block("load"):
                vii, vjj = T.axis.remap("SS", [i, j])
                B_frag[vii, vjj] = B[vii, vjj]


@T.prim_func
def wmma_m16n16k16_load_b_impl(b: T.handle, b_frag: T.handle) -> None:
    s0 = T.var("int32")
    s1 = T.var("int32")
    B = T.match_buffer(b, (16, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="shared",
                       strides=[s0, s1])
    B_frag = T.match_buffer(b_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_b")
    with T.block("root"):
        T.reads(B[0:16, 0:16])
        T.writes(B_frag[0:16, 0:16])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_load_matrix_sync(
                    B_frag.data,
                    16,
                    16,
                    16,
                    B_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(B_frag.elem_offset, 256), 16),
                    B.access_ptr("r"),
                    B.strides[0],
                    "row_major",
                    dtype="handle",
                ))


@T.prim_func
def wmma_m8n32k16_load_b_desc(b: T.handle, b_frag: T.handle) -> None:
    B = T.match_buffer(b, (16, 32),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="shared")
    B_frag = T.match_buffer(b_frag, (16, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_b")
    with T.block("root"):
        for i, j in T.grid(16, 32):
            with T.block("load"):
                vii, vjj = T.axis.remap("SS", [i, j])
                B_frag[vii, vjj] = B[vii, vjj]


@T.prim_func
def wmma_m8n32k16_load_b_impl(b: T.handle, b_frag: T.handle) -> None:
    s0 = T.var("int32")
    s1 = T.var("int32")
    B = T.match_buffer(b, (16, 32),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="shared",
                       strides=[s0, s1])
    B_frag = T.match_buffer(b_frag, (16, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.matrix_b")
    with T.block("root"):
        T.reads(B[0:16, 0:32])
        T.writes(B_frag[0:16, 0:32])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_load_matrix_sync(
                    B_frag.data,
                    8,
                    32,
                    16,
                    B_frag.elem_offset // 512 +
                    T.floordiv(T.floormod(B_frag.elem_offset, 512), 32),
                    B.access_ptr("r"),
                    B.strides[0],
                    "row_major",
                    dtype="handle",
                ))


@T.prim_func
def wmma_m16n16k16_fill_desc(c_frag: T.handle) -> None:
    C_frag = T.match_buffer(c_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    with T.block("root"):
        for i, j in T.grid(16, 16):
            with T.block("init"):
                vii, vjj = T.axis.remap("SS", [i, j])
                C_frag[vii, vjj] = T.float16(0)


@T.prim_func
def wmma_m16n16k16_fill_impl(c_frag: T.handle) -> None:
    C_frag = T.match_buffer(c_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    with T.block("root"):
        T.reads([])
        T.writes(C_frag[0:16, 0:16])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_fill_fragment(
                    C_frag.data,
                    16,
                    16,
                    16,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 16),
                    T.float16(0),
                    dtype="handle",
                ))


@T.prim_func
def wmma_m8n32k16_fill_desc(c_frag: T.handle) -> None:
    C_frag = T.match_buffer(c_frag, (8, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    with T.block("root"):
        for i, j in T.grid(8, 32):
            with T.block("init"):
                vii, vjj = T.axis.remap("SS", [i, j])
                C_frag[vii, vjj] = T.float16(0)


@T.prim_func
def wmma_m8n32k16_fill_impl(c_frag: T.handle) -> None:
    C_frag = T.match_buffer(c_frag, (8, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    with T.block("root"):
        T.reads([])
        T.writes(C_frag[0:8, 0:32])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_fill_fragment(
                    C_frag.data,
                    8,
                    32,
                    16,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 32),
                    T.float16(0),
                    dtype="handle",
                ))


@T.prim_func
def wmma_m16n16k16_store_desc(c_frag: T.handle, c: T.handle) -> None:
    C_frag = T.match_buffer(c_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    C = T.match_buffer(c, (16, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global")
    with T.block("root"):
        for i, j in T.grid(16, 16):
            with T.block("store"):
                vii, vjj = T.axis.remap("SS", [i, j])
                C[vii, vjj] = C_frag[vii, vjj]


@T.prim_func
def wmma_m16n16k16_store_impl(c_frag: T.handle, c: T.handle) -> None:
    s0 = T.var("int32")
    s1 = T.var("int32")
    C_frag = T.match_buffer(c_frag, (16, 16),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    C = T.match_buffer(c, (16, 16),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global",
                       strides=[s0, s1])
    with T.block("root"):
        T.reads(C_frag[0:16, 0:16])
        T.writes(C[0:16, 0:16])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_store_matrix_sync(
                    C_frag.data,
                    16,
                    16,
                    16,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 16),
                    C.access_ptr("w"),
                    C.strides[0],
                    "row_major",
                    dtype="handle",
                ))


@T.prim_func
def wmma_m8n32k16_store_desc(c_frag: T.handle, c: T.handle) -> None:
    C_frag = T.match_buffer(c_frag, (8, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    C = T.match_buffer(c, (8, 32),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global")
    with T.block("root"):
        for i, j in T.grid(8, 32):
            with T.block("store"):
                vii, vjj = T.axis.remap("SS", [i, j])
                C[vii, vjj] = C_frag[vii, vjj]


@T.prim_func
def wmma_m8n32k16_store_impl(c_frag: T.handle, c: T.handle) -> None:
    s0 = T.var("int32")
    s1 = T.var("int32")
    C_frag = T.match_buffer(c_frag, (8, 32),
                            "float16",
                            align=128,
                            offset_factor=16,
                            scope="wmma.accumulator")
    C = T.match_buffer(c, (8, 32),
                       "float16",
                       align=128,
                       offset_factor=16,
                       scope="global",
                       strides=[s0, s1])
    with T.block("root"):
        T.reads(C_frag[0:8, 0:32])
        T.writes(C[0:8, 0:32])
        for tx in T.thread_binding(0, 32, "threadIdx.x"):
            T.evaluate(
                T.tvm_store_matrix_sync(
                    C_frag.data,
                    8,
                    32,
                    16,
                    C_frag.elem_offset // 256 +
                    T.floordiv(T.floormod(C_frag.elem_offset, 256), 32),
                    C.access_ptr("w"),
                    C.strides[0],
                    "row_major",
                    dtype="handle",
                ))


WMMA_M16N16K16_SYNC = tir.TensorIntrin.register(
    "wmma_m16n16k16_sync",
    wmma_m16n16k16_sync_desc,
    wmma_m16n16k16_sync_impl,
)

WMMA_M8N32K16_SYNC = tir.TensorIntrin.register(
    "wmma_m8n32k16_sync",
    wmma_m8n32k16_sync_desc,
    wmma_m8n32k16_sync_impl,
)

WMMA_M16N16K16_LOAD_A = tir.TensorIntrin.register(
    "wmma_m16n16k16_load_a",
    wmma_m16n16k16_load_a_desc,
    wmma_m16n16k16_load_a_impl,
)

WMMA_M8N32K16_LOAD_A = tir.TensorIntrin.register(
    "wmma_m8n32k16_load_a",
    wmma_m8n32k16_load_a_desc,
    wmma_m8n32k16_load_a_impl,
)

WMMA_M16N16K16_LOAD_B = tir.TensorIntrin.register(
    "wmma_m16n16k16_load_b",
    wmma_m16n16k16_load_b_desc,
    wmma_m16n16k16_load_b_impl,
)

WMMA_M8N32K16_LOAD_B = tir.TensorIntrin.register(
    "wmma_m8n32k16_load_b",
    wmma_m8n32k16_load_b_desc,
    wmma_m8n32k16_load_b_impl,
)

WMMA_M16N16K16_FILL = tir.TensorIntrin.register(
    "wmma_m16n16k16_fill",
    wmma_m16n16k16_fill_desc,
    wmma_m16n16k16_fill_impl,
)

WMMA_M8N32K16_FILL = tir.TensorIntrin.register(
    "wmma_m8n32k16_fill",
    wmma_m8n32k16_fill_desc,
    wmma_m8n32k16_fill_impl,
)

WMMA_M16N16K16_STORE = tir.TensorIntrin.register(
    "wmma_m16n16k16_store",
    wmma_m16n16k16_store_desc,
    wmma_m16n16k16_store_impl,
)

WMMA_M8N32K16_STORE = tir.TensorIntrin.register(
    "wmma_m8n32k16_store",
    wmma_m8n32k16_store_desc,
    wmma_m8n32k16_store_impl,
)


@T.prim_func
def tcspmm(
    a: T.handle,
    b: T.handle,
    c: T.handle,
    indptr: T.handle,
    indices: T.handle,
    mb: T.int32,
    nb: T.int32,
    nnzb: T.int32,
    feat_size: T.int32,
    tile_size: T.int32,
    group_size: T.int32,
) -> None:
    T.func_attr({
        "global_symbol": "main",
        "tir.noalias": True,
        "sparse_tir_level": 2,
    })
    IO = T.dense_fixed(mb)
    JO = T.dense_variable(IO, (nb, nnzb), indptr, "int32")
    II = T.dense_fixed(tile_size)
    JI = T.sparse_fixed(JO, (nb * group_size, group_size), indices, "int32")
    I = T.dense_fixed(mb * tile_size)
    J = T.dense_fixed(nb * group_size)
    F = T.dense_fixed(feat_size)
    A = T.match_sparse_buffer(a, [IO, JO, II, JI], "float16")
    B = T.match_sparse_buffer(b, [J, F], "float16")
    C = T.match_sparse_buffer(c, [I, F], "float16")

    with T.iter([IO, JO, II, JI, F], "SRSRS", "tcspmm") as [io, jo, ii, ji, f]:
        with T.init():
            C[io * tile_size + ii, f] = T.float16(0)
        C[io * tile_size + ii,
          f] = C[io * tile_size + ii, f] + A[io, jo, ii, ji] * B[ji, f]


def parse_mma_shape(mma_shape_str: str):
    m_pos = 0
    n_pos = mma_shape_str.index("n")
    k_pos = mma_shape_str.index("k")
    return (
        int(mma_shape_str[m_pos + 1:n_pos]),
        int(mma_shape_str[n_pos + 1:k_pos]),
        int(mma_shape_str[k_pos + 1:]),
    )


def bench_tc_spmm(sp_mat: Any, x: th.Tensor, mma_shape_str: str):
    mma_m, mma_n, mma_k = parse_mma_shape(mma_shape_str)
    indptr, indices = sp_mat.indptr, sp_mat.indices
    indptr_nd = tvm.nd.array(indptr.astype("int32"), device=tvm.cpu())
    indices_nd = tvm.nd.array(indices.astype("int32"), device=tvm.cpu())
    tile_size = mma_m
    group_size = mma_k
    m, n = sp_mat.shape
    nnz = sp_mat.nnz
    mb = (m + tile_size - 1) // tile_size
    nb = (n + group_size - 1) // group_size
    group_indptr, tile_indices, mask, _, _, _ = condense(indptr_nd,
                                                         indices_nd,
                                                         tile_size,
                                                         group_size,
                                                         threshold=1)
    print("Con-dense density: {}".format(
        np.prod(mask.numpy().shape) / (m * n)))
    del indptr_nd, indices_nd
    nnzb = mask.shape[0]
    feat_size = x.shape[1]
    x = th.concat([
        x,
        th.zeros(
            (nb * group_size - n, feat_size), dtype=x.dtype, device=x.device)
    ],
                  dim=0)

    MB, NB, NNZB, F, T, G = tcspmm.params[-6:]
    mod = tvm.IRModule.from_expr(
        tcspmm.specialize({
            MB: mb,
            NB: nb,
            NNZB: nnzb,
            F: feat_size,
            T: tile_size,
            G: group_size,
        }))
    mod = lower_sparse_iter(mod)
    sch = tir.Schedule(mod)
    blk_outer = sch.get_block("tcspmm0")
    blk_inner = sch.get_block("tcspmm1")
    (i, ) = sch.get_loops(blk_outer)
    sch.bind(i, "blockIdx.x")
    jo, ii, ji, f = sch.get_loops(blk_inner)
    foo, foi, fi = sch.split(f, [None, min(1, feat_size // mma_n), mma_n])
    sch.bind(foo, "blockIdx.y")
    # sch.unroll(foi)
    sch.reorder(foo, foi, jo, ii, ji, fi)
    blk_inner_outer, blk_inner_inner = sch.blockize(ii), blk_inner
    A_wmma = sch.cache_read(blk_inner_inner, 1, "wmma.matrix_a")
    B_shared = sch.reverse_cache_read(blk_inner_inner, 2, "shared")
    B_wmma = sch.reverse_cache_read(blk_inner_inner, 2, "wmma.matrix_b")
    C_wmma = sch.cache_write(blk_inner_outer, 0, "wmma.accumulator")
    sch.reverse_compute_at(C_wmma, foi)
    init_blk = sch.decompose_reduction(blk_inner_outer, jo)
    sch.hide_buffer_access(blk_inner_inner, "read", [3])
    sch.tensorize(
        sch.get_loops(A_wmma)[-2], "wmma_{}_load_a".format(mma_shape_str))
    sch.tensorize(
        sch.get_loops(C_wmma)[-2], "wmma_{}_store".format(mma_shape_str))
    sch.tensorize(
        sch.get_loops(B_wmma)[-2], "wmma_{}_load_b".format(mma_shape_str))
    sch.tensorize(
        sch.get_loops(blk_inner_inner)[-3],
        "wmma_{}_sync".format(mma_shape_str))
    ax0, ax1 = sch.get_loops(B_shared)
    ax = sch.fuse(ax0, ax1)
    warp_size = 32
    vector_length = 8
    ax0, ax1, ax2 = sch.split(ax, [None, warp_size, vector_length])
    sch.unroll(ax0)
    sch.bind(ax1, "threadIdx.x")
    sch.vectorize(ax2)
    sch.tensorize(
        sch.get_loops(sch.get_block("tcspmm1_init"))[-2],
        "wmma_{}_fill".format(mma_shape_str))

    mod = lower_sparse_buffer(sch.mod)
    f = tvm.build(mod, target="cuda")
    # print(f.imported_modules[0].get_source())
    # assert False

    # prepare input
    dev = tvm.cuda(0)
    a_nd = tvm.nd.array(mask.numpy().astype("float16").flatten(), device=dev)
    b_nd = tvm.nd.array(x.cpu().numpy().flatten(), device=dev)
    c_nd = tvm.nd.array(np.zeros(mb * tile_size * feat_size).astype("float16"),
                        device=dev)
    indptr_nd = tvm.nd.array(group_indptr.numpy().astype("int32"), device=dev)
    indices_nd = tvm.nd.array(tile_indices.numpy().astype("int32").flatten(),
                              device=dev)
    args = [a_nd, b_nd, c_nd, indptr_nd, indices_nd]
    # f(*args)

    evaluator = f.time_evaluator(f.entry_name, tvm.cuda(0), number=100)
    avg_time = evaluator(*args).mean
    print("tc-spmm time: \t{:.5f}ms".format(avg_time * 1000))
    return avg_time


def matmul(a, b):
    return a @ b


def bench_cublas(W: th.Tensor, X: th.Tensor):
    with th.no_grad():
        W = W.half().to(0)
        X = X.to(0)
        timer = benchmark.Timer(stmt="matmul(a, b)",
                                setup="from __main__ import matmul",
                                globals={
                                    'a': W,
                                    'b': X
                                })
        measure = timer.timeit(100)

        print("cublas time: \t{:.5f}ms".format(measure.mean * 1000))
        return measure.mean


def bench_cusparse(csr: Any, X: th.Tensor):
    W = th.sparse_csr_tensor(csr.indptr,
                             csr.indices,
                             csr.data,
                             size=csr.shape,
                             dtype=th.float16).to(0)
    with th.no_grad():
        W = W.half().to(0)
        X = X.to(0)
        timer = benchmark.Timer(stmt="matmul(a, b)",
                                setup="from __main__ import matmul",
                                globals={
                                    'a': W,
                                    'b': X
                                })
        measure = timer.timeit(100)

        print("cusparse time: \t{:.5f}ms".format(measure.mean * 1000))
        return measure.mean


if __name__ == "__main__":
    parser = argparse.ArgumentParser("structured prunned bert")
    parser.add_argument("--dim",
                        "-d",
                        type=int,
                        default=128,
                        help="feature size")
    parser.add_argument("--csv",
                        "-c",
                        action="store_true",
                        help="whether to dump csv file or not")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(
        "huggingface/prunebert-base-uncased-6-finepruned-w-distil-squad")

    model = AutoModelForQuestionAnswering.from_pretrained(
        "huggingface/prunebert-base-uncased-6-finepruned-w-distil-squad")

    # question, text = "Who was Jim Henson?", "Jim Henson was a nice puppet"

    # inputs = tokenizer(question, text, return_tensors="pt")

    # with th.no_grad():
    #     outputs = model(**inputs)

    # answer_start_index = outputs.start_logits.argmax()
    # answer_end_index = outputs.end_logits.argmax()

    # predict_answer_tokens = inputs.input_ids[0, answer_start_index : answer_end_index + 1]
    # print(tokenizer.decode(predict_answer_tokens))

    # W * X: W: (64, 32) X: (32, 128)
    nnz_params = 0
    ttl_params = 0
    for name, param in model.named_parameters():
        if name.endswith("dense.weight") or name.endswith(
                "key.weight") or name.endswith(
                    "value.weight") or name.endswith("query.weight"):
            ttl_params += param.numel()
            nnz_params += len(param.nonzero())

    print(nnz_params / ttl_params)

    sparsetir_durs = []
    cublas_durs = []
    cusparse_durs = []
    densities = []
    for name, param in model.named_parameters():
        if name.endswith("dense.weight") or name.endswith(
                "key.weight") or name.endswith(
                    "value.weight") or name.endswith("query.weight"):
            csr_weight = sp.csr_matrix(param.detach().numpy())
            print("Density: {:.5f}".format(csr_weight.nnz / param.numel()))
            densities.append(csr_weight.nnz / param.numel())
            print(param.shape)
            x = th.rand(csr_weight.shape[1], args.dim).half()
            sparsetir_durs.append(bench_tc_spmm(csr_weight, x, "m8n32k16"))
            cublas_durs.append(bench_cublas(param.data, x))
            cusparse_durs.append(bench_cusparse(csr_weight, x))

    print(sum(sparsetir_durs), sum(cublas_durs), sum(cusparse_durs))
    if args.csv:
        pd = pd.DataFrame(
            data={
                "density": densities,
                "sparsetir_dur": sparsetir_durs,
                "cublas_dur": cublas_durs,
                "cusparse_dur": cusparse_durs
            })
        pd.to_csv("single_op.csv", index=False)