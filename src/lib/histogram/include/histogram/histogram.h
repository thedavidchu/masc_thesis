#pragma once

#include <stdbool.h>
#include <stdint.h>

/// @brief  This histogram tracks (potentially scaled) equal-sized values.
/// @note   I assume no overflow in any of these values!
struct Histogram {
    uint64_t *histogram;
    /// Number of bins in the histogram
    uint64_t num_bins;
    // Size of each bin
    uint64_t bin_size;
    /// We have seen this before, but we do not track stacks this large
    uint64_t false_infinity;
    /// We have not seen this before
    uint64_t infinity;
    uint64_t running_sum;
};

bool
Histogram__init(struct Histogram *me,
                const uint64_t num_bins,
                const uint64_t bin_size);

bool
Histogram__insert_finite(struct Histogram *me, const uint64_t index);

/// @brief  Insert a non-infinite, scaled index. By scaled, I mean that the
///         index represents multiple elements.
/// @note   This is used for SHARDS.
bool
Histogram__insert_scaled_finite(struct Histogram *me,
                                const uint64_t index,
                                const uint64_t scale);

bool
Histogram__insert_infinite(struct Histogram *me);

bool
Histogram__insert_scaled_infinite(struct Histogram *me, const uint64_t scale);

bool
Histogram__exactly_equal(struct Histogram *me, struct Histogram *other);

void
Histogram__print_as_json(struct Histogram *me);

void
Histogram__destroy(struct Histogram *me);
