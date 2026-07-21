#include "tanuki_progress.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#define INCBIN_SILENCE_BITCODE_WARNING
#include "incbin/incbin.h"

#include "misc.h"
#include "position.h"
#include "testcmd/unit_test.h"

using namespace YaneuraOu;

namespace {

// 進行度係数ファイルのパス。LS_* 系 (LS_BUCKET_MODE 等) の命名に合わせる。
constexpr char kLsProgressCoeff[] = "LS_PROGRESS_COEFF";
constexpr char kLsBucketMode[] = "LS_BUCKET_MODE";
constexpr char kInternalPath[] = "<internal>";

// logit((i+1)/8) を Q16.16 に丸めた閾値 + 番兵
static constexpr int64_t kMaxAbsSumQ16 =
    static_cast<int64_t>(YaneuraOu::PIECE_NUMBER_KING) * 2 * static_cast<int64_t>(INT32_MAX);
static constexpr int64_t kThresholdsQ16[8] = {
    -127527, -71999, -33477, 0, 33477, 71999, 127527, kMaxAbsSumQ16 + 1,
};

constexpr double kQ16Scale = 65536.0;
constexpr int kWeightCount = static_cast<int>(YaneuraOu::SQ_NB) * static_cast<int>(YaneuraOu::Eval::fe_end);
constexpr size_t kRawWeightsBytes = kWeightCount * sizeof(double);

YaneuraOu::OptionsMap* g_options = nullptr;
int32_t g_weights_q16[YaneuraOu::SQ_NB][YaneuraOu::Eval::fe_end] = {};

enum class BucketModeRequest {
    Auto,
    KingRank9,
    Progress8KPAbs,
    Progress8Ek,
};

BucketModeRequest g_bucket_mode_request = BucketModeRequest::Progress8KPAbs;
Tanuki::Progress::BucketMode g_bucket_mode = Tanuki::Progress::BucketMode::KingRank9;
int g_layer_stacks = 1;
bool g_layer_stacks_configured = false;
bool g_progress_loaded = false;

const char* bucket_mode_name(Tanuki::Progress::BucketMode mode) {
    switch (mode) {
    case Tanuki::Progress::BucketMode::First:
        return "first";
    case Tanuki::Progress::BucketMode::KingRank9:
        return "kingrank9";
    case Tanuki::Progress::BucketMode::Progress8KPAbs:
        return "progress8kpabs";
    case Tanuki::Progress::BucketMode::Progress8Ek:
        return "progress8ek";
    }
    return "unknown";
}

Tanuki::Progress::BucketMode fallback_bucket_mode() {
    if (g_progress_loaded && g_layer_stacks >= 8)
        return Tanuki::Progress::BucketMode::Progress8KPAbs;
    return Tanuki::Progress::BucketMode::First;
}

void warn_bucket_fallback(const char* requested, int required, Tanuki::Progress::BucketMode fallback) {
    sync_cout << "info string Warning: LS_BUCKET_MODE " << requested << " requires LayerStacks>="
              << required << " (current " << g_layer_stacks << "), falling back to "
              << bucket_mode_name(fallback) << sync_endl;
}

void resolve_bucket_mode(bool warn) {
    Tanuki::Progress::BucketMode mode = Tanuki::Progress::BucketMode::KingRank9;

    switch (g_bucket_mode_request) {
    case BucketModeRequest::Auto:
        mode = g_progress_loaded ? Tanuki::Progress::BucketMode::Progress8KPAbs
                                 : Tanuki::Progress::BucketMode::KingRank9;
        break;
    case BucketModeRequest::KingRank9:
        mode = Tanuki::Progress::BucketMode::KingRank9;
        break;
    case BucketModeRequest::Progress8KPAbs:
        mode = Tanuki::Progress::BucketMode::Progress8KPAbs;
        break;
    case BucketModeRequest::Progress8Ek:
        mode = Tanuki::Progress::BucketMode::Progress8Ek;
        break;
    }

    if (mode == Tanuki::Progress::BucketMode::KingRank9 && g_layer_stacks < 9) {
        const auto fallback = fallback_bucket_mode();
        if (warn)
            warn_bucket_fallback("kingrank9", 9, fallback);
        mode = fallback;
    }

    if (mode == Tanuki::Progress::BucketMode::Progress8Ek && g_layer_stacks < 9) {
        const auto fallback = fallback_bucket_mode();
        if (warn)
            warn_bucket_fallback("progress8ek", 9, fallback);
        mode = fallback;
    }

    if (mode == Tanuki::Progress::BucketMode::Progress8KPAbs && g_layer_stacks < 8) {
        const auto fallback = Tanuki::Progress::BucketMode::First;
        if (warn)
            warn_bucket_fallback("progress8kpabs", 8, fallback);
        mode = fallback;
    }

    if ((mode == Tanuki::Progress::BucketMode::Progress8KPAbs
         || mode == Tanuki::Progress::BucketMode::Progress8Ek)
        && !g_progress_loaded) {
        const char* requested = bucket_mode_name(mode);
        const auto fallback = g_layer_stacks >= 9 ? Tanuki::Progress::BucketMode::KingRank9
                                                  : Tanuki::Progress::BucketMode::First;
        if (warn)
            sync_cout << "info string Warning: LS_BUCKET_MODE " << requested
                      << " requires a loaded progress file, falling back to "
                      << bucket_mode_name(fallback) << sync_endl;
        mode = fallback;
    }

    g_bucket_mode = mode;
}

int32_t to_q16(double value) {
    const double scaled = std::round(value * kQ16Scale);
    const double clamped = std::clamp(scaled, static_cast<double>(INT32_MIN), static_cast<double>(INT32_MAX));
    return static_cast<int32_t>(clamped);
}

void load_weights_from_raw(const double* raw_weights) {
    for (int sq = 0; sq < YaneuraOu::SQ_NB; ++sq) {
        for (int piece = 0; piece < YaneuraOu::Eval::fe_end; ++piece) {
            const int index = sq * static_cast<int>(YaneuraOu::Eval::fe_end) + piece;
            g_weights_q16[sq][piece] = to_q16(raw_weights[index]);
        }
    }
}

inline int32_t contribution(YaneuraOu::Square sq, int bona_piece) {
    return g_weights_q16[sq][bona_piece];
}

int32_t compute_full_sum_q16(const YaneuraOu::Position& pos, YaneuraOu::Square sq_bk, YaneuraOu::Square sq_wk) {
    const auto& list0 = pos.eval_list()->piece_list_fb();
    const auto& list1 = pos.eval_list()->piece_list_fw();

    int32_t sum_q16 = 0;
    for (int i = 0; i < YaneuraOu::PIECE_NUMBER_KING; ++i) {
        sum_q16 += contribution(sq_bk, list0[i]);
        sum_q16 += contribution(sq_wk, list1[i]);
    }
    return sum_q16;
}

bool try_get_sum_from_cache(const YaneuraOu::Position& pos, YaneuraOu::Square sq_bk, YaneuraOu::Square sq_wk,
                            int32_t& sum_q16) {
    auto* st = pos.state();
    if (!st->tanuki_progress_valid) return false;
    if (st->tanuki_progress_key != pos.key()) return false;
    if (st->tanuki_progress_sq_bk != sq_bk || st->tanuki_progress_sq_wk != sq_wk) return false;

    sum_q16 = st->tanuki_progress_sum;
    return true;
}

void store_sum_cache(const YaneuraOu::Position& pos, YaneuraOu::Square sq_bk, YaneuraOu::Square sq_wk, int32_t sum_q16) {
    auto* st = pos.state();
    st->tanuki_progress_key = pos.key();
    st->tanuki_progress_sum = sum_q16;
    st->tanuki_progress_sq_bk = sq_bk;
    st->tanuki_progress_sq_wk = sq_wk;
    st->tanuki_progress_valid = true;
}

int table_index_linear_q16(int32_t sum_q16) {
    int idx = 0;
    while (sum_q16 >= kThresholdsQ16[idx]) {
        ++idx;
    }
    return idx;
}

#if !defined(_MSC_VER)
INCBIN(EmbeddedProgress, "progress.bin");
#else
const unsigned char gEmbeddedProgressData[1] = {0};
const unsigned char* const gEmbeddedProgressEnd = &gEmbeddedProgressData[1];
const unsigned int gEmbeddedProgressSize = 1;
#endif

}  // namespace

namespace Tanuki {
namespace Progress {

bool add_options(YaneuraOu::OptionsMap& options) {
    g_options = &options;
    options.add(kLsProgressCoeff, YaneuraOu::Option(kInternalPath));
#if defined(SFNNwoPSQT)
    options.add(kLsBucketMode,
                YaneuraOu::Option(std::vector<std::string>{"auto", "kingrank9", "progress8kpabs", "progress8ek"}, "progress8kpabs",
                                  [](const YaneuraOu::Option& o) {
                                      const std::string mode = std::string(o);
                                      if (mode == "progress8ek")
                                          g_bucket_mode_request = BucketModeRequest::Progress8Ek;
                                      else if (mode == "progress8kpabs")
                                          g_bucket_mode_request = BucketModeRequest::Progress8KPAbs;
                                      else if (mode == "kingrank9")
                                          g_bucket_mode_request = BucketModeRequest::KingRank9;
                                      else
                                          g_bucket_mode_request = BucketModeRequest::Auto;

                                      if (g_layer_stacks_configured)
                                          resolve_bucket_mode(true);
                                      return std::nullopt;
                                  }));
#endif
    return true;
}

void SetLayerStackCount(int layer_stacks) {
    g_layer_stacks = layer_stacks;
    g_layer_stacks_configured = true;
    resolve_bucket_mode(false);
}

BucketMode CurrentBucketMode() {
    return g_bucket_mode;
}

bool Load() {
    if (g_options == nullptr) {
        sync_cout << "info string Progress options are not initialized." << sync_endl;
        g_progress_loaded = false;
        resolve_bucket_mode(g_layer_stacks_configured);
        return false;
    }

    const std::string file_path = (*g_options)[kLsProgressCoeff];

    if (file_path == kInternalPath) {
        if (gEmbeddedProgressSize != kRawWeightsBytes) {
            sync_cout << "info string Embedded progress size mismatch. expected=" << kRawWeightsBytes
                      << " actual=" << gEmbeddedProgressSize << sync_endl;
            g_progress_loaded = false;
            resolve_bucket_mode(g_layer_stacks_configured);
            return false;
        }

        std::vector<double> raw_weights(kWeightCount);
        std::memcpy(raw_weights.data(), gEmbeddedProgressData, kRawWeightsBytes);
        load_weights_from_raw(raw_weights.data());
        sync_cout << "info string loading progress file : <internal>" << sync_endl;
        g_progress_loaded = true;
        resolve_bucket_mode(g_layer_stacks_configured);
        return true;
    }

    std::ifstream stream(file_path, std::ios::binary);
    if (!stream.is_open()) {
        sync_cout << "info string Failed to open the progress file. file_path=" << file_path << sync_endl;
        g_progress_loaded = false;
        resolve_bucket_mode(g_layer_stacks_configured);
        return false;
    }

    std::vector<double> raw_weights(kWeightCount);
    stream.read(reinterpret_cast<char*>(raw_weights.data()), kRawWeightsBytes);
    if (!stream) {
        sync_cout << "info string Failed to read the progress file. file_path=" << file_path << sync_endl;
        g_progress_loaded = false;
        resolve_bucket_mode(g_layer_stacks_configured);
        return false;
    }

    load_weights_from_raw(raw_weights.data());
    sync_cout << "info string loading progress file : " << file_path << sync_endl;
    g_progress_loaded = true;
    resolve_bucket_mode(g_layer_stacks_configured);
    return true;
}

int LayerStackIndex(const YaneuraOu::Position& pos) {
    const auto sq_bk = pos.square<YaneuraOu::KING>(YaneuraOu::BLACK);
    const auto sq_wk = YaneuraOu::Inv(pos.square<YaneuraOu::KING>(YaneuraOu::WHITE));

    int32_t sum_q16 = 0;
    if (!try_get_sum_from_cache(pos, sq_bk, sq_wk, sum_q16)) {
        sum_q16 = compute_full_sum_q16(pos, sq_bk, sq_wk);
        store_sum_cache(pos, sq_bk, sq_wk, sum_q16);
    }

    int idx = table_index_linear_q16(sum_q16);
    return idx;
}

bool IsMutualEnteringKing(const YaneuraOu::Position& pos) {
    const auto black_king_rank = YaneuraOu::rank_of(pos.square<YaneuraOu::KING>(YaneuraOu::BLACK));
    const auto white_king_rank = YaneuraOu::rank_of(pos.square<YaneuraOu::KING>(YaneuraOu::WHITE));
    return black_king_rank <= YaneuraOu::RANK_5 && white_king_rank >= YaneuraOu::RANK_5;
}

int LayerStackIndexProgress8Ek(const YaneuraOu::Position& pos) {
    // 相入玉局面ではprogress係数を参照せず、9番目のLayerStackを選ぶ。
    if (IsMutualEnteringKing(pos))
        return 8;
    return LayerStackIndex(pos);
}

void UnitTest(YaneuraOu::Test::UnitTester& tester, YaneuraOu::IEngine&) {
    auto section = tester.section("Tanuki::Progress");

    YaneuraOu::Position pos;
    YaneuraOu::StateInfo state;
    auto set = [&](const std::string& sfen) { pos.set(sfen, &state); };

    set("lnsg1gsnl/1r5b1/ppppppppp/9/K7k/9/PPPPPPPPP/1B5R1/LNSG1GSNL b - 1");
    tester.test("双方の玉が五段目なら相入玉", IsMutualEnteringKing(pos));
    tester.test("相入玉は9番目のLayerStack", LayerStackIndexProgress8Ek(pos) == 8);

    set("lnsg1gsnl/1r5b1/ppppppppp/K8/9/8k/PPPPPPPPP/1B5R1/LNSG1GSNL w - 1");
    tester.test("双方の玉が五段目を越えても相入玉", IsMutualEnteringKing(pos));
    tester.test("相入玉判定は手番に依存しない", LayerStackIndexProgress8Ek(pos) == 8);

    set("lnsg1gsnl/1r5b1/ppppppppp/9/8k/K8/PPPPPPPPP/1B5R1/LNSG1GSNL b - 1");
    tester.test("先手玉が六段目なら相入玉ではない", !IsMutualEnteringKing(pos));
    tester.test("非相入玉は従来のprogress indexと一致",
                LayerStackIndexProgress8Ek(pos) == LayerStackIndex(pos));

    set("lnsg1gsnl/1r5b1/ppppppppp/8k/K8/9/PPPPPPPPP/1B5R1/LNSG1GSNL b - 1");
    tester.test("後手玉が四段目なら相入玉ではない", !IsMutualEnteringKing(pos));
    tester.test("後手境界外も従来indexと一致",
                LayerStackIndexProgress8Ek(pos) == LayerStackIndex(pos));
}

}  // namespace Progress
}  // namespace Tanuki
