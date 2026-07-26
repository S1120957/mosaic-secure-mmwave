#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr std::size_t kFrames = 10;
constexpr std::size_t kChirps = 16;
constexpr std::size_t kRx = 4;
constexpr std::size_t kSamples = 256;
constexpr std::size_t kComponents = 2;
constexpr double kC0 = 299792458.0;
constexpr double kFs = 5209e3;
constexpr double kSlope = 57.14e12;

std::vector<std::int16_t> read_i16(const std::string& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw std::runtime_error("Cannot open " + path);
    const auto bytes = static_cast<std::size_t>(in.tellg());
    const std::size_t expected =
        kFrames * kChirps * kRx * kSamples * kComponents * sizeof(std::int16_t);
    if (bytes != expected) {
        throw std::runtime_error(
            "Unexpected file size for " + path + ": " + std::to_string(bytes)
        );
    }
    in.seekg(0);
    std::vector<std::int16_t> data(bytes / sizeof(std::int16_t));
    in.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(bytes));
    if (!in) throw std::runtime_error("Short read from " + path);
    return data;
}

std::size_t offset(
    std::size_t frame,
    std::size_t chirp,
    std::size_t rx,
    std::size_t sample
) {
    return (((frame * kChirps + chirp) * kRx + rx) * kSamples + sample)
           * kComponents;
}

std::vector<double> mean_range_power(const std::vector<std::int16_t>& raw) {
    std::vector<double> power(kSamples / 2, 0.0);
    const double pi = std::acos(-1.0);
    for (std::size_t f = 0; f < kFrames; ++f) {
        for (std::size_t c = 0; c < kChirps; ++c) {
            for (std::size_t r = 0; r < kRx; ++r) {
                for (std::size_t bin = 0; bin < kSamples / 2; ++bin) {
                    std::complex<double> acc(0.0, 0.0);
                    for (std::size_t n = 0; n < kSamples; ++n) {
                        const auto idx = offset(f, c, r, n);
                        const double q = static_cast<double>(raw[idx]);
                        const double i = static_cast<double>(raw[idx + 1]);
                        const double w =
                            0.5 - 0.5 * std::cos(2.0 * pi * n / (kSamples - 1));
                        const double angle =
                            -2.0 * pi * static_cast<double>(bin * n) / kSamples;
                        acc += std::complex<double>(i, q)
                               * w
                               * std::complex<double>(
                                     std::cos(angle), std::sin(angle));
                    }
                    power[bin] += std::norm(acc);
                }
            }
        }
    }
    const double denominator =
        static_cast<double>(kFrames * kChirps * kRx);
    for (auto& value : power) value /= denominator;
    return power;
}

double range_for_bin(std::size_t bin) {
    const double beat_hz = static_cast<double>(bin) * kFs / kSamples;
    return kC0 * beat_hz / (2.0 * kSlope);
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: validate_real_data TARGET_BIN BACKGROUND_BIN\n";
        return 64;
    }
    try {
        const auto target = read_i16(argv[1]);
        const auto background = read_i16(argv[2]);
        const auto target_power = mean_range_power(target);
        const auto background_power = mean_range_power(background);

        std::vector<double> differential(target_power.size(), 0.0);
        for (std::size_t i = 0; i < differential.size(); ++i) {
            differential[i] = std::max(0.0, target_power[i] - background_power[i]);
        }

        std::vector<std::size_t> indices(differential.size());
        for (std::size_t i = 0; i < indices.size(); ++i) indices[i] = i;
        std::partial_sort(
            indices.begin(), indices.begin() + 10, indices.end(),
            [&](std::size_t a, std::size_t b) {
                return differential[a] > differential[b];
            }
        );

        const bool primary_ok = indices[0] == 46;
        const auto secondary_it = std::find(indices.begin(), indices.begin() + 10, 13);
        const bool secondary_ok = secondary_it != indices.begin() + 10;

        std::cout << std::fixed << std::setprecision(6);
        std::cout << "{\n";
        std::cout << "  \"logical_shape_per_frame\": [16, 256, 4],\n";
        std::cout << "  \"primary_peak_bin\": " << indices[0] << ",\n";
        std::cout << "  \"primary_peak_range_m\": " << range_for_bin(indices[0]) << ",\n";
        std::cout << "  \"secondary_bin_13_range_m\": " << range_for_bin(13) << ",\n";
        std::cout << "  \"top_10_bins\": [";
        for (std::size_t i = 0; i < 10; ++i) {
            if (i) std::cout << ", ";
            std::cout << indices[i];
        }
        std::cout << "],\n";
        std::cout << "  \"overall_pass\": "
                  << ((primary_ok && secondary_ok) ? "true" : "false") << "\n";
        std::cout << "}\n";
        return (primary_ok && secondary_ok) ? 0 : 2;
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << "\n";
        return 1;
    }
}
