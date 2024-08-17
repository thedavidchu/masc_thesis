"""Analyze a log file for timing information."""

import argparse
import re
import os
from difflib import SequenceMatcher
from pathlib import Path
from warnings import warn

import matplotlib.pyplot as plt
from tqdm import tqdm


def check_no_matches(*args) -> bool:
    """Check that all of the arguments are unique (or are None).

    Examples
    --------
    1. {1, 2, None, None} -> True
    2. {0, 0} -> False
    """
    num_none = sum(arg is None for arg in args)
    num_unique = len({arg for arg in args if arg is not None})
    return len(args) == num_none + num_unique


# NOTE  I do not support spaces or control characters in paths.
PATH_PATTERN = r"[a-zA-Z0-9_./\\-]+"
FLOAT_PATTERN = r"\d+[.]\d+"


def get_log_pattern(level: str, pattern: str) -> str:
    assert level in "VERBOSE,TRACE,DEBUG,INFO,WARN,ERROR,FATAL".split(",")
    return rf"^\[{level}\] \[\d+-\d+-\d+ \d+:\d+:\d+\] \[ {PATH_PATTERN}:\d+ \] \[errno \d+: [^\]]*\] {pattern}"


def get_file_tree(path: Path | list[Path]) -> list[Path]:
    """Return a list of all the files belonging to a directory."""
    if isinstance(path, list):
        return [file for dir_or_file in path for file in get_file_tree(dir_or_file)]
    if os.path.isfile(path):
        return [path]
    return [
        Path(os.path.join(dirpath, f)).absolute()
        for dirpath, dirnames, filenames in os.walk(path)
        for f in filenames
    ]


def get_file_stems(path: list[str]) -> list[str]:
    return [os.path.splitext(os.path.split(p)[-1])[0] for p in path]


def get_longest_substring(*args: str) -> str:
    """
    I originally copied this code from
    https://www.geeksforgeeks.org/sequencematcher-in-python-for-longest-common-substring/.
    Of course, they had a syntax error, because what would online source
    code if not buggy?

    I fixed the syntax error and probably spent longer on that than I
    would have if I had just written the darn thing myself.

    So I rewrote it and read the documentation. Wow, imagine that.
    """

    def get_longest_substring_twoway(a: str, b: str) -> str:
        s = SequenceMatcher(isjunk=None, a=a, b=b)
        alo, blo, size = s.find_longest_match(0, len(a), 0, len(b))
        assert a[alo : alo + size] == b[blo : blo + size]
        return a[alo : alo + size]

    # Pattern matching is your friend! Wow, that was so easy... I just
    # hope that it actually works, haha!
    match args:
        case []:
            # Maybe we should return None. I'm too tired to think.
            return ""
        case [x]:
            return x
        case [x, y]:
            # I think this case may be redundant considering the case
            # below, but this is more symmetric and therefore easier to
            # reason about.
            return get_longest_substring_twoway(x, y)
        case [x, y, *z]:
            return get_longest_substring(get_longest_substring_twoway(x, y), *z)


def get_trace_read_time_from_log(text: str, path: Path) -> float:
    pattern = re.compile(
        get_log_pattern("INFO", rf"Trace Read Time: ({FLOAT_PATTERN}) sec$")
    )
    matching_lines = [
        re.match(pattern, line)
        for line in text.splitlines()
        if re.match(pattern, line) is not None
    ]
    if len(matching_lines) == 0:
        warn(f"log {path} has no trace time")
        return 0.0
    if len(matching_lines) > 1:
        raise ValueError(f"log {path} has multiple trace times")
    time = float(matching_lines[0].group(1))
    return time


def get_compute_time_from_log(text: str, path: Path) -> dict[str, float]:
    pattern = re.compile(
        get_log_pattern(
            "INFO",
            rf"({PATH_PATTERN}) -- Histogram Time: ({FLOAT_PATTERN}) [|] Post-Process Time: ({FLOAT_PATTERN}) [|] MRC Time: ({FLOAT_PATTERN}) [|] Total Time: ({FLOAT_PATTERN})$",
        )
    )
    matching_lines = [
        re.match(pattern, line)
        for line in text.splitlines()
        if re.match(pattern, line) is not None
    ]
    if len(matching_lines) == 0:
        # NOTE  Some experiments did not finish
        # TODO  Remove this short-circuit once Kia makes the disks
        #       read/write again and I can run the remaining Olken
        #       traces.
        warn(f"log {path} has no compute time")
        return {}
    return {l.group(1): float(l.group(5)) for l in matching_lines}


def plot_runtime(
    inputs: list[Path],
    extensions: list[str],
    outputs: list[Path],
    algorithms: list[str],
):
    all_compute_times = {algo: {} for algo in algorithms}
    for file in get_file_tree(inputs):
        if file.suffix not in extensions:
            continue
        with file.open() as f:
            text = f.read()
        ttime = get_trace_read_time_from_log(text, file)
        ctimes = get_compute_time_from_log(text, file)
        for algo, ctime in ctimes.items():
            print(
                f"Times for {str(file)}:{algo} -- Trace read: {ttime} | Total compute: {ctime}"
            )
            if algo in algorithms:
                all_compute_times[algo][str(file)] = ctime
    all_compute_times = {
        algo: {k: v for k, v in sorted(times_.items())}
        for algo, times_ in all_compute_times.items()
    }
    fig, axs = plt.subplots()
    fig.set_size_inches(12, 8)
    fig.suptitle("Runtimes by Trace")
    fig.supxlabel("Trace Name")
    fig.supylabel("Runtimes [seconds]")
    for algo, times_ in all_compute_times.items():
        pretty_label = algo.replace("-", " ")
        axs.plot([t for t in times_.values()], label=pretty_label)
    axs.legend()

    # Add labels to the axis
    all_stems = {
        algo: get_file_stems(times_.keys())
        for algo, times_ in all_compute_times.items()
    }
    labels = [
        get_longest_substring(*stems).strip(" \t_-./")
        for stems in zip(*all_stems.values())
    ]
    axs.set_xticks(
        range(len(labels)),
        labels,
        rotation=90,
    )
    for output in outputs:
        fig.savefig(output)


def get_accuracy_from_log(text: str, path: Path) -> dict[str, tuple[float, float]]:
    pattern = re.compile(
        get_log_pattern(
            "INFO",
            rf"({PATH_PATTERN}) -- Mean Absolute Error \(MAE\): ({FLOAT_PATTERN}) [|] Mean Squared Error \(MSE\): ({FLOAT_PATTERN})",
        )
    )
    matching_lines = [
        re.match(pattern, line)
        for line in text.splitlines()
        if re.match(pattern, line) is not None
    ]
    if len(matching_lines) == 0:
        warn(f"log {path} has no accuracy")
        return {}
    # NOTE  I no longer explicit name them here, but the first float is
    #       the MAE and the second is the MSE.
    return {l.group(1): (float(l.group(2)), float(l.group(3))) for l in matching_lines}


def plot_accuracy(inputs: list[Path], extensions: list[str], outputs: list[Path]):
    emap_accuracies = {}
    fss_accuracies = {}
    for file in tqdm(get_file_tree(inputs)):
        if file.suffix not in extensions:
            continue
        with file.open() as f:
            text = f.read()
        accuracies = get_accuracy_from_log(text, file)
        for algo, (mae, mse) in accuracies.items():
            print(f"Accuracies for {str(file)}:{algo} -- MAE: {mae} | MSE: {mse}")
            if "Evicting-Map" == algo:
                emap_accuracies[str(file)] = mae
            elif "Fixed-Size-SHARDS" == algo:
                fss_accuracies[str(file)] = mae
    emap_accuracies = {k: v for k, v in sorted(emap_accuracies.items())}
    fss_accuracies = {k: v for k, v in sorted(fss_accuracies.items())}
    fig, axs = plt.subplots()
    fig.set_size_inches(12, 8)
    fig.suptitle("Mean Absolute Error (MAE) by Trace")
    fig.supxlabel("Trace Name")
    fig.supylabel("Mean Absolute Error (MAE) [%]")
    axs.plot(
        [100 * x for x in emap_accuracies.values()],
        label="Evicting Map",
    )
    axs.plot([100 * x for x in fss_accuracies.values()], label="Fixed-Size SHARDS")

    emap_stems = get_file_stems(emap_accuracies.keys())
    fss_stems = get_file_stems(fss_accuracies.keys())
    labels = [
        get_longest_substring(emap_stem, fss_stem).strip(" \t_-./")
        for emap_stem, fss_stem in zip(emap_stems, fss_stems)
    ]
    axs.set_xticks(
        range(len(labels)),
        labels,
        rotation=90,
    )
    axs.legend()
    for output in outputs:
        fig.savefig(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs", "-i", nargs="+", type=Path, help="file/directory of input(s)"
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        type=str,
        default=[".log"],
        help="extensions to process (format: '--extensions .log .csv')",
    )
    parser.add_argument(
        "--time",
        nargs="*",
        type=Path,
        default=None,
        help="specifying this will plot runtime. Default: time.pdf (ignore what Python says). You can replace this with your own custom names!",
    )
    parser.add_argument(
        "--olken-time",
        nargs="*",
        type=Path,
        default=None,
        help="specifying this will plot Olken runtime. Default: olken-time.pdf (ignore what Python says). You can replace this with your own custom names!",
    )
    parser.add_argument(
        "--accuracy",
        nargs="*",
        type=Path,
        default=None,
        help="specifying this will plot accuracy. Default: accuracy.pdf (ignore what Python says). You can replace this with your own custom names!",
    )
    args = parser.parse_args()

    if not check_no_matches(*args.time, *args.accuracy, *args.olken_time):
        raise ValueError(
            f"duplicate values in {args.time, args.accuracy, args.olken_time}"
        )

    if args.time is not None:
        outputs = [Path("time.pdf")] if args.time == [] else args.time
        plot_runtime(
            args.inputs, args.extensions, outputs, ["Evicting-Map", "Fixed-Size-SHARDS"]
        )
    if args.olken_time is not None:
        outputs = [Path("olken-time.pdf")] if args.olken_time == [] else args.olken_time
        plot_runtime(args.inputs, args.extensions, outputs, ["Olken"])
    if args.accuracy is not None:
        outputs = [Path("accuracy.pdf")] if args.accuracy == [] else args.accuracy
        plot_accuracy(args.inputs, args.extensions, outputs)


if __name__ == "__main__":
    main()
