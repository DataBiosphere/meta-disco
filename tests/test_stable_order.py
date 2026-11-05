"""The order a report lists things in, taken from the things themselves (#732)."""

from collections import Counter

from meta_disco.stable_order import by_file_name, keep_smallest, most_frequent, past_smallest


def test_the_most_frequent_strings_tie_by_the_string_whatever_order_they_were_counted_in():
    """A producer counts from many threads; its metadata must not depend on which finished first."""
    a = Counter({"b": 1, "a": 1, "c": 2})
    b = Counter({"c": 2, "a": 1, "b": 1})
    assert list(most_frequent(a)) == list(most_frequent(b)) == ["c", "a", "b"]
    assert most_frequent(a, 2) == {"c": 2, "a": 1}


def test_the_examples_kept_are_the_smallest_whatever_order_they_arrive_in():
    names = ["e.bam", "b.bam", "d.bam", "a.bam", "c.bam"]
    kept_forward: list = []
    kept_back: list = []
    for name in names:
        keep_smallest(kept_forward, name, 3)
    for name in reversed(names):
        keep_smallest(kept_back, name, 3)
    assert kept_forward == kept_back == ["a.bam", "b.bam", "c.bam"]


def test_examples_that_are_not_strings_are_ordered_by_their_content():
    one, two = {"file_name": "a", "role": "y"}, {"role": "x", "file_name": "a"}
    kept_forward: list = []
    kept_back: list = []
    for example in (one, two):
        keep_smallest(kept_forward, example, 2)
    for example in (two, one):
        keep_smallest(kept_back, example, 2)
    assert kept_forward == kept_back == [two, one]


def test_an_example_naming_a_file_is_kept_by_its_file_name_whatever_else_it_holds():
    late, early = {"activity": "A", "file_name": "b.bam"}, {"activity": "Z", "file_name": "a.bam"}
    kept: list = []
    for example in (late, early):
        keep_smallest(kept, example, 1, key=by_file_name)
    assert kept == [early]


def test_a_name_repeated_across_folders_is_kept_once():
    """Files sharing a base name sort together; one must not fill every slot."""
    kept: list = []
    for name in ("output.vcf.gz", "output.vcf.gz", "output.vcf.gz", "z.vcf.gz"):
        keep_smallest(kept, name, 3)
    assert kept == ["output.vcf.gz", "z.vcf.gz"]


def test_an_example_past_the_smallest_is_known_before_it_is_built():
    kept: list = []
    for name in ("b.bam", "a.bam"):
        keep_smallest(kept, {"file_name": name}, 2, key=by_file_name)
    assert past_smallest(kept, "c.bam", 2)
    assert not past_smallest(kept, "b.bam", 2)  # an equal name may still sort before by content
    assert not past_smallest(kept, "c.bam", 3)
