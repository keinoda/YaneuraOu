// NNUE評価関数の差分計算用のクラス

#ifndef CLASSIC_NNUE_ACCUMULATOR_H_
#define CLASSIC_NNUE_ACCUMULATOR_H_

#include "../../config.h"

#if defined(EVAL_NNUE)

#include "nnue_architecture.h"

#if defined(USE_NNUE_FINNY_TABLES) && !defined(SFNNwoPSQT)
#error "USE_NNUE_FINNY_TABLES requires an SFNNwoPSQT architecture"
#endif

#if defined(USE_NNUE_FINNY_PIECE_LIST) && !defined(USE_NNUE_FINNY_TABLES)
#error "USE_NNUE_FINNY_PIECE_LIST requires USE_NNUE_FINNY_TABLES"
#endif

namespace YaneuraOu {
namespace Eval::NNUE {

// 入力特徴量をアフィン変換した結果を保持するクラス
// 最終的な出力である評価値も一緒に持たせておく
// AVX-512命令を使用する場合に64bytesのアライメントが要求される。
struct alignas(64) Accumulator {
  std::int16_t
      accumulation[2][kRefreshTriggers.size()][kTransformedFeatureDimensions];
  Value score = VALUE_ZERO;
  bool computed_accumulation = false;
  bool computed_score = false;
};

#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)

// Finny Tables cache one fully refreshed accumulator for each
// perspective-specific king square.
static constexpr IndexType kFinnyMaxActiveFeatures =
    RawFeatures::kMaxActiveDimensions;

struct alignas(64) FinnyCacheEntry {
  std::int16_t accumulation[kTransformedFeatureDimensions];
#if defined(USE_NNUE_FINNY_PIECE_LIST)
  // Experimental HalfKA_hm2 path: compare the 40 stable PieceList slots
  // directly instead of generating and sorting active feature indices.
  BonaPiece piece_list[PIECE_NUMBER_NB];
#else
  IndexType active_indices[kFinnyMaxActiveFeatures];
  std::uint16_t num_active = 0;
#endif
  bool valid = false;
};

struct FinnyTable {
  FinnyCacheEntry entries[SQ_NB][COLOR_NB];
  std::uint64_t generation = 0;

  void invalidate(std::uint64_t new_generation) {
    for (auto& square_entries : entries)
      for (auto& entry : square_entries)
        entry.valid = false;
    generation = new_generation;
  }
};

#endif

} // namespace Eval::NNUE
} // namespace YaneuraOu

#endif  // defined(EVAL_NNUE)

#endif
