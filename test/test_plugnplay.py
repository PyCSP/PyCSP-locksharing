#!/usr/bin/env python3

"""Testing the plugNplay module.
"""

from pycsp import Channel, process, Parallel, Sequence, Alternative
from pycsp.plugNplay import Identity, Prefix, Delta2, ParDelta2, SeqDelta2, AltDelta2
from pycsp.plugNplay import Successor, SkipProcess, Mux2

# sometimes N is good enough.
# pylint: disable=invalid-name


@process(verbose_poison=True)
def write_vals(vals, cout):
    """Write each value from the sequence vals out to cout, one by one"""
    for v in vals:
        cout(v)
    print(f"write_vals done writing {len(vals)} messages")


@process
def read_n(N, cin):
    """Read N values from cin and terminate, returning a list of the read values."""
    vals = [cin() for _ in range(N)]
    print(f"read_vals done reading {len(vals)} messages")
    return vals


@process
def write_vals_and_poison(vals, cout):
    """Write each value from the sequence vals out to cout, one by one.
    Then poison the channel."""
    for v in vals:
        cout(v)
    print(f"write_vals_and_poison poisoning channnel {cout}")
    cout.poison()


@process
def read_n_and_poison(N, cin):
    """Read N values from cin and terminate, returning a list of the read values.
    Then poison the channel.
    """
    vals = [cin() for _ in range(N)]
    print(f"read_n_and_poison poisoning channnel {cin} after {len(vals)} reads")
    cin.poison()
    return vals


def test_identity():
    """Test the Identity process."""
    print("\nTesting Identity")
    print("-------------------")
    N = 10
    vals = list(range(N))
    ch1 = Channel('ch1')
    ch2 = Channel('ch2')
    rets = Parallel(
        # Try to write more than the reader needs
        write_vals(vals * 2, ch1.write),
        Identity(ch1.read, ch2.write),
        # The reader should be able to poison the rest when it is satisfied
        read_n_and_poison(N, ch2.read)
    )
    print(rets)
    assert vals == rets[-1], f"Identity: write {vals} do not match read {rets[-1]}"


def test_prefix_poison_read_end():
    """Test the Prefix process
    It poisons the read end, which is the wrong end to apply poison, so it demonstrates
    a trick to make the poison propagate properly.
    """
    print("\nTest the Prefix process")
    print("-------------------")

    # TODO: pycsp parallel and sequence cannot be composed like aPyCSP equivalents.
    # Need to do this instead.
    @process
    def run_read():
        """Internal helper
        The poison cannot propagate up through Prefix if prefix is waiting on ch1.read, so
        we need to poison both ends.
        This little trick poisons channel 1 after channel 2."""
        rets = Sequence(read_n_and_poison(len(vals), ch2.read))
        print("Now poisoning ch1")
        ch1.poison()
        return rets[0]

    vals = list(range(10))
    ch1 = Channel('ch1')
    ch2 = Channel('ch2')
    rets = Parallel(
        write_vals(vals[1:], ch1.write),
        Prefix(ch1.read, ch2.write, vals[0]),
        run_read())
    assert rets[-1] == vals, "Should get the same values back as the ones written {vals} {rets[-1]}"


def test_prefix_poison_write_end():
    """Test the Prefix process"""
    print("\nTest the Prefix process, poioning writer")
    print("-------------------")

    vals = list(range(10))
    ch1 = Channel('ch1')
    ch2 = Channel('ch2')
    # The last reader should complete reading before channel is poisoned, so the values
    # should be returned.
    rets = Parallel(
        write_vals_and_poison(vals[1:], ch1.write),
        Prefix(ch1.read, ch2.write, vals[0]),
        read_n(len(vals), ch2.read))

    assert rets[-1] == vals, "Should get the same values back as the ones written {vals} {rets[-1]}"


def delta_tester(delta_proc):
    """Helper function to test the delta processes"""
    print("\nTesting the {delta_proc} process")
    print("-------------------")
    vals = list(range(10))
    ch1 = Channel('ch1')
    ch2 = Channel('ch2')
    ch3 = Channel('ch3')
    # Need to apply poison to kill the delta process.
    rets = Parallel(
        write_vals_and_poison(vals, ch1.write),
        delta_proc(ch1.read, ch2.write, ch3.write),
        read_n(len(vals), ch2.read),
        read_n(len(vals), ch3.read))
    assert rets[-1] == vals, "Should get the same values back as the ones written {vals} {rets[-1]}"
    assert rets[-2] == vals, "Should get the same values back as the ones written {vals} {rets[-2]}"

    # TODO: timing testing is harder. Considering letting each writer and reader timestamp before and
    # after each operation, pass it back here and then examine the timestamp traces to verify that
    # everything happens in the same order.


def test_delta2():
    """Test the Delta2 process"""
    delta_tester(Delta2)


def test_par_delta2():
    """Test the ParDelta2 process"""
    delta_tester(ParDelta2)


def test_seq_delta2():
    """Test the SeqDelta2 process"""
    delta_tester(SeqDelta2)


def test_alt_delta2():
    """Test the AltDelta2 process"""
    delta_tester(AltDelta2)


def test_successor():
    """Test the Successor process."""
    print("\nTesting Successor")
    print("-------------------")
    vals = list(range(11))
    ch1 = Channel()
    ch2 = Channel()
    rets = Parallel(
        write_vals_and_poison(vals[:-1], ch1.write),
        Successor(ch1.read, ch2.write),
        read_n(len(vals) - 1, ch2.read))
    assert rets[-1] == vals[1:], f"Should get values increased by one. Got {rets[-1]}"


def test_mux2():
    "Test the Mux2 process"""
    # TODO: This exposes two issues at the moment.
    # - poison propagation is immediate. If one writer finishes early on ch1, the other
    #   writer will be poisoned before it can complete.
    #   This is better handled by the retire() mechanism that is not currently implemented.
    # - pycsp does not implement composable Sequence and Parallel constructs equivalent to aPyCSP,
    #   so that type of composability is done by adding new processes like this:
    def gen_vals(pid):
        return [(pid, v) for v in vals]

    @process
    def write_both_then_poison():
        # Let each write id + val
        Parallel(
            write_vals(gen_vals(1), ch1.write),
            write_vals(gen_vals(2), ch2.write))
        ch1.poison()

    print("\nTesting Mux2")
    print("-------------------")
    vals = list(range(10))
    ch1 = Channel('ch1')
    ch2 = Channel('ch2')
    ch3 = Channel('ch3')
    rets = Parallel(
        write_both_then_poison(),
        Mux2(ch1.read, ch2.read, ch3.write),
        read_n(len(vals) * 2, ch3.read))
    print("Got from reader", rets[-1])
    rvals = sorted(rets[-1])
    expected = sorted(gen_vals(1) + gen_vals(2))
    assert rvals == expected, f"Expected to get all values sent from writer. Got {rets[-1]}"


if __name__ == "__main__":
    test_identity()
    test_prefix_poison_read_end()
    test_prefix_poison_write_end()
    test_delta2()
    test_par_delta2()
    test_seq_delta2()
    test_alt_delta2()
    test_successor()
    test_mux2()
