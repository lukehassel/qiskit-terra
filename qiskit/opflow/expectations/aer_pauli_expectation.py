# This code is part of Qiskit.
#
# (C) Copyright IBM 2020.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

""" AerPauliExpectation Class """

import logging
from typing import Union

from qiskit.exceptions import MissingOptionalLibraryError
from qiskit.opflow.expectations.expectation_base import ExpectationBase
from qiskit.opflow.list_ops.composed_op import ComposedOp
from qiskit.opflow.list_ops.list_op import ListOp
from qiskit.opflow.list_ops.summed_op import SummedOp
from qiskit.opflow.operator_base import OperatorBase
from qiskit.opflow.primitive_ops.pauli_op import PauliOp
from qiskit.opflow.primitive_ops.pauli_sum_op import PauliSumOp
from qiskit.opflow.state_fns.circuit_state_fn import CircuitStateFn
from qiskit.opflow.state_fns.operator_state_fn import OperatorStateFn

logger = logging.getLogger(__name__)


class AerPauliExpectation(ExpectationBase):
    r"""An Expectation converter for using Aer's operator snapshot to
    take expectations of quantum state circuits over Pauli observables.

    """

    def convert(self, operator: OperatorBase) -> OperatorBase:
        """Accept an Operator and return a new Operator with the Pauli measurements replaced by
        AerSnapshot-based expectation circuits.

        Args:
            operator: The operator to convert.

        Returns:
            The converted operator.
        """
        if isinstance(operator, OperatorStateFn) and operator.is_measurement:
            return self._replace_pauli_sums(operator.primitive) * operator.coeff
        elif isinstance(operator, ListOp):
            return operator.traverse(self.convert)
        else:
            return operator

    @classmethod
    def _replace_pauli_sums(cls, operator):
        try:
            from qiskit.providers.aer.extensions import SnapshotExpectationValue
        except ImportError as ex:
            raise MissingOptionalLibraryError(
                libname="qiskit-aer",
                name="AerPauliExpectation",
                pip_install="pip install qiskit-aer",
            ) from ex
        # The 'expval_measurement' label on the snapshot instruction is special - the
        # CircuitSampler will look for it to know that the circuit is a Expectation
        # measurement, and not simply a
        # circuit to replace with a DictStateFn
        if operator.__class__ == ListOp:
            return operator.traverse(cls._replace_pauli_sums)

        if isinstance(operator, PauliSumOp):
            paulis = [(meas[1], meas[0]) for meas in operator.primitive.to_list()]
            snapshot_instruction = SnapshotExpectationValue("expval_measurement", paulis)
            return CircuitStateFn(
                snapshot_instruction, coeff=operator.coeff, is_measurement=True, from_operator=True
            )

        # Change to Pauli representation if necessary
        if {"Pauli"} != operator.primitive_strings():
            logger.warning(
                "Measured Observable is not composed of only Paulis, converting to "
                "Pauli representation, which can be expensive."
            )
            # Setting massive=False because this conversion is implicit. User can perform this
            # action on the Observable with massive=True explicitly if they so choose.
            operator = operator.to_pauli_op(massive=False)

        if isinstance(operator, SummedOp):
            paulis = [[meas.coeff, meas.primitive] for meas in operator.oplist]
            snapshot_instruction = SnapshotExpectationValue("expval_measurement", paulis)
            return CircuitStateFn(snapshot_instruction, is_measurement=True, from_operator=True)
        if isinstance(operator, PauliOp):
            paulis = [[operator.coeff, operator.primitive]]
            snapshot_instruction = SnapshotExpectationValue("expval_measurement", paulis)
            return CircuitStateFn(snapshot_instruction, is_measurement=True, from_operator=True)

        raise TypeError(
            f"Conversion of OperatorStateFn of {operator.__class__.__name__} is not defined."
        )

    def compute_variance(self, exp_op: OperatorBase) -> Union[list, float]:
        r"""
        Compute the variance of the expectation estimator. Because Aer takes this expectation
        with matrix multiplication, the estimation is exact and the variance is always 0,
        but we need to return those values in a way which matches the Operator's structure.

        Args:
            exp_op: The full expectation value Operator after sampling.

        Returns:
             The variances or lists thereof (if exp_op contains ListOps) of the expectation value
             estimation, equal to 0.
        """

        # Need to do this to mimic Op structure
        def sum_variance(operator):
            if isinstance(operator, ComposedOp):
                return 0.0
            elif isinstance(operator, ListOp):
                return operator._combo_fn([sum_variance(op) for op in operator.oplist])
            raise TypeError(f"Variance cannot be computed for {operator.__class__.__name__}.")

        return sum_variance(exp_op)
