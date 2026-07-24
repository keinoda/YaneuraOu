// A class that converts the input features of the NNUE evaluation function
// NNUE評価関数の入力特徴量の変換を行うクラス

#ifndef CLASSIC_NNUE_FEATURE_TRANSFORMER_H_INCLUDED
#define CLASSIC_NNUE_FEATURE_TRANSFORMER_H_INCLUDED

#include "../../config.h"

#if defined(EVAL_NNUE)

#if defined(SFNNwoPSQT)
#define USE_ELEMENT_WISE_MULTIPLY
#endif

#include "nnue_common.h"
#include "nnue_architecture.h"
#include "features/index_list.h"
#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)
#include "features/feature_set.h"
#include "features/half_ka_hm2.h"
#endif

#include <algorithm>  // std::clamp
#include <cstring>  // std::memset()
#include <type_traits>

namespace YaneuraOu {
namespace Eval::NNUE {

// If vector instructions are enabled, we update and refresh the
// accumulator tile by tile such that each tile fits in the CPU's
// vector registers.
// ベクトル命令が有効な場合、変数のタイルを、
// 各タイルがCPUのベクトルレジスタに収まるように、更新してリフレッシュする。
#define VECTOR

#if defined(USE_AVX512)
using vec_t = __m512i;
#define vec_load(a) _mm512_load_si512(a)
#define vec_store(a, b) _mm512_store_si512(a, b)
#define vec_add_16(a, b) _mm512_add_epi16(a, b)
#define vec_sub_16(a, b) _mm512_sub_epi16(a, b)
#define vec_mulhi_16(a, b) _mm512_mulhi_epi16(a, b)
#define vec_set_16(a) _mm512_set1_epi16(a)
#define vec_max_16(a, b) _mm512_max_epi16(a, b)
#define vec_min_16(a, b) _mm512_min_epi16(a, b)
#define vec_slli_16(a, b) _mm512_slli_epi16(a, b)
#define vec_packus_16(a, b) _mm512_packus_epi16(a, b)
#define vec_zero() _mm512_setzero_si512()
static constexpr IndexType kNumRegs = 8;  // only 8 are needed

#elif defined(USE_AVX2)
using vec_t = __m256i;
#define vec_load(a) _mm256_load_si256(a)
#define vec_store(a, b) _mm256_store_si256(a, b)
#define vec_add_16(a, b) _mm256_add_epi16(a, b)
#define vec_sub_16(a, b) _mm256_sub_epi16(a, b)
#define vec_mulhi_16(a, b) _mm256_mulhi_epi16(a, b)
#define vec_set_16(a) _mm256_set1_epi16(a)
#define vec_max_16(a, b) _mm256_max_epi16(a, b)
#define vec_min_16(a, b) _mm256_min_epi16(a, b)
#define vec_slli_16(a, b) _mm256_slli_epi16(a, b)
#define vec_packus_16(a, b) _mm256_packus_epi16(a, b)
#define vec_zero() _mm256_setzero_si256()
static constexpr IndexType kNumRegs = 16;

#elif defined(USE_SSE2)
using vec_t = __m128i;
#define vec_load(a) (*(a))
#define vec_store(a, b) *(a) = (b)
#define vec_add_16(a, b) _mm_add_epi16(a, b)
#define vec_sub_16(a, b) _mm_sub_epi16(a, b)
#define vec_mulhi_16(a, b) _mm_mulhi_epi16(a, b)
#define vec_set_16(a) _mm_set1_epi16(a)
#define vec_max_16(a, b) _mm_max_epi16(a, b)
#define vec_min_16(a, b) _mm_min_epi16(a, b)
#define vec_slli_16(a, b) _mm_slli_epi16(a, b)
#define vec_packus_16(a, b) _mm_packus_epi16(a, b)
#define vec_zero() _mm_setzero_si128()
static constexpr IndexType kNumRegs = Is64Bit ? 16 : 8;

#elif defined(USE_MMX)
using vec_t = __m64;
#define vec_load(a) (*(a))
#define vec_store(a, b) *(a) = (b)
#define vec_add_16(a, b) _mm_add_pi16(a, b)
#define vec_sub_16(a, b) _mm_sub_pi16(a, b)
#define vec_zero() _mm_setzero_si64()
static constexpr IndexType kNumRegs = 8;

#elif defined(USE_NEON)
using vec_t = int16x8_t;
#define vec_load(a) (*(a))
#define vec_store(a, b) *(a) = (b)
#define vec_add_16(a, b) vaddq_s16(a, b)
#define vec_sub_16(a, b) vsubq_s16(a, b)
#define vec_mulhi_16(a, b) vqdmulhq_s16(a, b)
#define vec_set_16(a) vdupq_n_s16(a)
#define vec_max_16(a, b) vmaxq_s16(a, b)
#define vec_min_16(a, b) vminq_s16(a, b)
#define vec_slli_16(a, b) vshlq_s16(a, vec_set_16(b))
#define vec_packus_16(a, b) reinterpret_cast<vec_t>(vcombine_u8(vqmovun_s16(a), vqmovun_s16(b)))
#define vec_zero() \
	vec_t { 0 }
static constexpr IndexType kNumRegs = 16;

#else
#undef VECTOR

#endif

/*
 例) SFNN1536のときのkNumChunksの計算

┌─────────┬───────────────┬─────────────────┬────────────┐
│  SIMD            │ sizeof(vec_t)                │ / sizeof(int16)                  │ kNumChunks             │
├─────────┼───────────────┼─────────────────┼────────────┤
│ AVX-512          │ 64                           │ 32                               │ 1536/32=48             │
├─────────┼───────────────┼─────────────────┼────────────┤
│ AVX2             │ 32                           │ 16                               │ 1536/16=96             │
├─────────┼───────────────┼─────────────────┼────────────┤
│ SSE2             │ 16                           │ 8                                │ 1536/8=192             │
├─────────┼───────────────┼─────────────────┼────────────┤
│ NEON             │ 16                           │ 8                                │ 1536/8=192             │
└─────────┴───────────────┴─────────────────┴────────────┘
*/

constexpr IndexType MaxChunkSize = 16;

// Input feature converter
// 入力特徴量変換器
class FeatureTransformer {
   private:
	// Number of output dimensions for one side
	// 片側分の出力の次元数
	static constexpr IndexType kHalfDimensions = kTransformedFeatureDimensions;

#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)
	using FinnyPieceRawFeatures = Features::FeatureSet<
		Features::HalfKA_hm2<Features::Side::kFriend>>;
	static constexpr bool kUseFinnyPieceList =
		std::is_same<RawFeatures, FinnyPieceRawFeatures>::value;
#endif

#if defined(VECTOR)
	//static constexpr IndexType kTileHeight = kNumRegs * sizeof(vec_t) / 2;
	//static_assert(kHalfDimensions % kTileHeight == 0, "kTileHeight must divide kHalfDimensions");
	// ⇨  AVX-512でこの制約守れないっぽ。
#endif

   public:
	// Output type
	// 出力の型
	using OutputType = TransformedFeatureType;
	using BiasType   = std::int16_t;
	using WeightType = std::int16_t;

	// Number of input/output dimensions
	// 入出力の次元数
	static constexpr IndexType kInputDimensions  = RawFeatures::kDimensions;
#if defined(USE_ELEMENT_WISE_MULTIPLY)
	static constexpr IndexType kOutputDimensions = kHalfDimensions;
#else
	static constexpr IndexType kOutputDimensions = kHalfDimensions * 2;
#endif

	// Size of forward propagation buffer
	// 順伝播用バッファのサイズ
	static constexpr std::size_t kBufferSize = kOutputDimensions * sizeof(OutputType);

	// Hash value embedded in the evaluation file
	// 評価関数ファイルに埋め込むハッシュ値
	static constexpr std::uint32_t GetHashValue() {
#if defined(SFNNwoPSQT)
		// 学習部と整合性とるの面倒なのでSFNNwoPSQTのときはこれに固定しておく。
		return 0x5f134ab8u;
#else
		return RawFeatures::kHashValue ^ kOutputDimensions;
#endif
	}

	// A string that represents the structure
	// 構造を表す文字列
	static std::string GetStructureString() {
		return RawFeatures::GetName() + "[" + std::to_string(kInputDimensions) + "->"
		       + std::to_string(kHalfDimensions) + "x2]";
	}

	// Read network parameters
	// パラメータを読み込む
	Tools::Result ReadParameters(std::istream& stream) {
#if defined(USE_ELEMENT_WISE_MULTIPLY)
		read_leb_128<BiasType>(stream, biases_, kHalfDimensions);
		read_leb_128<WeightType>(stream, weights_, kHalfDimensions * kInputDimensions);

#if defined(VECTOR)
		permute_weights(inverse_order_packs);
#endif
		scale_weights(true);
#else
		for (std::size_t i = 0; i < kHalfDimensions; ++i) biases_[i] = read_little_endian<BiasType>(stream);
		for (std::size_t i = 0; i < kHalfDimensions * kInputDimensions; ++i)
			weights_[i] = read_little_endian<WeightType>(stream);
#endif
		return !stream.fail() ? Tools::ResultCode::Ok : Tools::ResultCode::FileReadError;
	}

	// Write network parameters
	// パラメータを書き込む
	bool WriteParameters(std::ostream& stream) const {
		stream.write(reinterpret_cast<const char*>(biases_), kHalfDimensions * sizeof(BiasType));
		stream.write(reinterpret_cast<const char*>(weights_), kHalfDimensions * kInputDimensions * sizeof(WeightType));
		return !stream.fail();
	}

	// Proceed with the difference calculation if possible
	// 可能なら差分計算を進める
	bool UpdateAccumulatorIfPossible(const Position& pos) const {
		const auto now = pos.state();
		if (now->accumulator.computed_accumulation) {
			return true;
		}
		const auto prev = now->previous;
		if (prev && prev->accumulator.computed_accumulation) {
			update_accumulator(pos);
			return true;
		}
		return false;
	}

#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)
	// Finny-enabled immediate-parent update. Deliberately does not include the
	// separate multi-ply ancestor-search optimization.
	bool UpdateAccumulatorIfPossible(
		const Position& pos, FinnyTable& cache) const {
		const auto now = pos.state();
		if (now->accumulator.computed_accumulation)
			return true;

		const auto prev = now->previous;
		if (prev && prev->accumulator.computed_accumulation) {
			update_accumulator_with_cache(pos, cache);
			return true;
		}
		return false;
	}
#endif

	// Convert input features
	// 入力特徴量を変換する
	void Transform(
		const Position& pos, OutputType* output, bool refresh
#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)
		, FinnyTable& cache
#endif
	) const {
#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)
		if (refresh || !UpdateAccumulatorIfPossible(pos, cache)) {
			refresh_accumulator_with_cache(pos, cache);
		}
#else
		if (refresh || !UpdateAccumulatorIfPossible(pos)) {
			refresh_accumulator(pos);
		}
#endif
		const auto& accumulation = pos.state()->accumulator.accumulation;

#if defined(USE_ELEMENT_WISE_MULTIPLY)

#if defined(VECTOR)
			// Packed output is sizeof(vec_t) bytes for each SIMD register
#if defined(USE_AVX512)
			constexpr IndexType OutputChunkSize = 64;
#else
			constexpr IndexType OutputChunkSize = kSimdWidth;
#endif
		static_assert((kHalfDimensions / 2) % OutputChunkSize == 0);
		constexpr IndexType NumOutputChunks = kHalfDimensions / 2 / OutputChunkSize;

		vec_t Zero = vec_zero();
		vec_t One = vec_set_16(127 * 2);

		const Color perspectives[2] = { pos.side_to_move(), ~pos.side_to_move() };
		for (IndexType p = 0; p < 2; ++p) {
			const IndexType offset = (kHalfDimensions / 2) * p;

			const vec_t* in0 = reinterpret_cast<const vec_t*>(&(accumulation[perspectives[p]][0][0]));
			const vec_t* in1 = reinterpret_cast<const vec_t*>(&(accumulation[perspectives[p]][0][kHalfDimensions / 2]));
			vec_t* out = reinterpret_cast<vec_t*>(output + offset);

			constexpr int shift =
#if defined(USE_SSE2)
				7;
#else
				6;
#endif

			for (IndexType j = 0; j < NumOutputChunks; ++j)
			{
				const vec_t sum0a =
					vec_slli_16(vec_max_16(vec_min_16(in0[j * 2 + 0], One), Zero), shift);
				const vec_t sum0b =
					vec_slli_16(vec_max_16(vec_min_16(in0[j * 2 + 1], One), Zero), shift);
				const vec_t sum1a = vec_min_16(in1[j * 2 + 0], One);
				const vec_t sum1b = vec_min_16(in1[j * 2 + 1], One);

				const vec_t pa = vec_mulhi_16(sum0a, sum1a);
				const vec_t pb = vec_mulhi_16(sum0b, sum1b);

				out[j] = vec_packus_16(pa, pb);
			}

		}

#else
		const Color perspectives[2] = { pos.side_to_move(), ~pos.side_to_move() };
		for (IndexType p = 0; p < 2; ++p) {
			const IndexType offset = (kHalfDimensions / 2) * p;

			for (IndexType j = 0; j < kHalfDimensions / 2; ++j)
			{
				BiasType sum0 = accumulation[perspectives[p]][0][j];
				BiasType sum1 = accumulation[perspectives[p]][0][j + kHalfDimensions / 2];
				sum0 = std::clamp<BiasType>(sum0, 0, 127 * 2);
				sum1 = std::clamp<BiasType>(sum1, 0, 127 * 2);
				output[offset + j] = static_cast<OutputType>(unsigned(sum0 * sum1) / 512);
			}

		}
#endif

#else

		// 以下は旧NNUEのコード。
		// ループ本体がx86とNEONで異なる（2入力→1出力 vs 1入力→1出力）ため、
		// kNumChunksの意味自体がアーキテクチャごとに違うため、共通化しにくい。触らないことにする。

#if defined(USE_AVX512)
		constexpr IndexType kNumChunks = kHalfDimensions / (kSimdWidth * 2);
		static_assert(kHalfDimensions % (kSimdWidth * 2) == 0);
		const __m512i kControl = _mm512_setr_epi64(0, 2, 4, 6, 1, 3, 5, 7);
		const __m512i kZero    = _mm512_setzero_si512();

#elif defined(USE_AVX2)
		constexpr IndexType kNumChunks = kHalfDimensions / kSimdWidth;
		constexpr int       kControl   = 0b11011000;
		const __m256i       kZero      = _mm256_setzero_si256();

#elif defined(USE_SSE2)
		constexpr IndexType kNumChunks = kHalfDimensions / kSimdWidth;
#if defined(USE_SSE41)
		const __m128i kZero = _mm_setzero_si128();
#else  // SSE41非対応だがSSE2は使える環境
		const __m128i k0x80s = _mm_set1_epi8(-128);
#endif

#elif defined(USE_MMX)
		// USE_MMX を config.h では現状、有効化することがないので dead code
		constexpr IndexType kNumChunks = kHalfDimensions / kSimdWidth;
		const __m64         k0x80s     = _mm_set1_pi8(-128);

#elif defined(USE_NEON)
		constexpr IndexType kNumChunks = kHalfDimensions / (kSimdWidth / 2);
		const int8x8_t      kZero      = {0};
#endif
		const Color perspectives[2] = {pos.side_to_move(), ~pos.side_to_move()};
		for (IndexType p = 0; p < 2; ++p) {
			const IndexType offset = kHalfDimensions * p;
#if defined(USE_AVX512)
			auto out = reinterpret_cast<__m512i*>(&output[offset]);
			for (IndexType j = 0; j < kNumChunks; ++j) {
				__m512i sum0 =
				    _mm512_load_si512(&reinterpret_cast<const __m512i*>(accumulation[perspectives[p]][0])[j * 2 + 0]);
				__m512i sum1 =
				    _mm512_load_si512(&reinterpret_cast<const __m512i*>(accumulation[perspectives[p]][0])[j * 2 + 1]);
				for (IndexType i = 1; i < kRefreshTriggers.size(); ++i) {
					sum0 = _mm512_add_epi16(
					    sum0,
					    reinterpret_cast<const __m512i*>(accumulation[perspectives[p]][i])[j * 2 + 0]);
					sum1 = _mm512_add_epi16(
					    sum1,
					    reinterpret_cast<const __m512i*>(accumulation[perspectives[p]][i])[j * 2 + 1]);
				}
				_mm512_store_si512(&out[j], _mm512_permutexvar_epi64(
								 kControl, _mm512_max_epi8(_mm512_packs_epi16(sum0, sum1), kZero)));
			}

#elif defined(USE_AVX2)
			auto out = reinterpret_cast<__m256i*>(&output[offset]);
			for (IndexType j = 0; j < kNumChunks; ++j) {
					__m256i sum0 =
					    _mm256_loadu_si256(&reinterpret_cast<const __m256i*>(accumulation[perspectives[p]][0])[j * 2 + 0]);
					__m256i sum1 =
					    _mm256_loadu_si256(&reinterpret_cast<const __m256i*>(accumulation[perspectives[p]][0])[j * 2 + 1]);
					for (IndexType i = 1; i < kRefreshTriggers.size(); ++i) {
						sum0 = _mm256_add_epi16(
							sum0,
							_mm256_loadu_si256(&reinterpret_cast<const __m256i*>(accumulation[perspectives[p]][i])[j * 2 + 0]));
						sum1 = _mm256_add_epi16(
							sum1,
							_mm256_loadu_si256(&reinterpret_cast<const __m256i*>(accumulation[perspectives[p]][i])[j * 2 + 1]));
					}
					_mm256_store_si256(&out[j], _mm256_permute4x64_epi64(
									 _mm256_max_epi8(_mm256_packs_epi16(sum0, sum1), kZero), kControl));
			}

#elif defined(USE_SSE2)
			auto out = reinterpret_cast<__m128i*>(&output[offset]);
			for (IndexType j = 0; j < kNumChunks; ++j) {
				__m128i sum0 =
				    _mm_load_si128(&reinterpret_cast<const __m128i*>(accumulation[perspectives[p]][0])[j * 2 + 0]);
				__m128i sum1 =
				    _mm_load_si128(&reinterpret_cast<const __m128i*>(accumulation[perspectives[p]][0])[j * 2 + 1]);
				for (IndexType i = 1; i < kRefreshTriggers.size(); ++i) {
					sum0 = _mm_add_epi16(sum0,
					                     reinterpret_cast<const __m128i*>(accumulation[perspectives[p]][i])[j * 2 + 0]);
					sum1 = _mm_add_epi16(sum1,
					                     reinterpret_cast<const __m128i*>(accumulation[perspectives[p]][i])[j * 2 + 1]);
				}

				const __m128i packedbytes = _mm_packs_epi16(sum0, sum1);
				_mm_store_si128(&out[j],
#if defined(USE_SSE41)
				                _mm_max_epi8(packedbytes, kZero)
#else  // SSE41非対応だがSSE2は使える環境
				                _mm_subs_epi8(_mm_adds_epi8(packedbytes, k0x80s), k0x80s)
#endif
				);
			}

#elif defined(USE_MMX)
			// USE_MMX を config.h では現状、有効化することがないので dead code
			auto out = reinterpret_cast<__m64*>(&output[offset]);
			for (IndexType j = 0; j < kNumChunks; ++j) {
				__m64       sum0 = *(&reinterpret_cast<const __m64*>(accumulation[perspectives[p]][0])[j * 2 + 0]);
				__m64       sum1 = *(&reinterpret_cast<const __m64*>(accumulation[perspectives[p]][0])[j * 2 + 1]);
				const __m64 packedbytes = _mm_packs_pi16(sum0, sum1);
				out[j]                  = _mm_subs_pi8(_mm_adds_pi8(packedbytes, k0x80s), k0x80s);
			}

#elif defined(USE_NEON)
			const auto out = reinterpret_cast<int8x8_t*>(&output[offset]);
			for (IndexType j = 0; j < kNumChunks; ++j) {
				int16x8_t sum = reinterpret_cast<const int16x8_t*>(accumulation[perspectives[p]][0])[j];
				for (IndexType i = 1; i < kRefreshTriggers.size(); ++i) {
					sum = vaddq_s16(sum, reinterpret_cast<const int16x8_t*>(accumulation[perspectives[p]][i])[j]);
				}
				out[j] = vmax_s8(vqmovn_s16(sum), kZero);
			}
#else
			for (IndexType j = 0; j < kHalfDimensions; ++j) {
				BiasType sum = accumulation[perspectives[p]][0][j];
				for (IndexType i = 1; i < kRefreshTriggers.size(); ++i) {
					sum += accumulation[perspectives[p]][i][j];
				}
				output[offset + j] = static_cast<OutputType>(std::clamp<int>(sum, 0, 127));
			}
#endif
		}
#if defined(USE_MMX)
		// USE_MMX を config.h では現状、有効化することがないので dead code
		_mm_empty();
#endif
#endif
	}

   private:
	static void order_packs([[maybe_unused]] uint64_t* v) {
#if defined(USE_AVX512)  // _mm512_set_epi32 packs in the order [15 11 7 3 14 10 6 2 13 9 5 1 12 8 4 0]
		uint64_t tmp0 = v[4], tmp1 = v[5];
		v[4] = v[6], v[5] = v[7];
		v[6] = tmp0, v[7] = tmp1;
		tmp0 = v[8], tmp1 = v[9];
		v[8] = v[12], v[9] = v[13];
		v[12] = v[10], v[13] = v[11];
		v[10] = tmp0, v[11] = tmp1;
#elif defined(USE_AVX2)  // _mm256_set_epi32 packs in the order [7 3 6 2 5 1 4 0]
		uint64_t tmp0 = v[2], tmp1 = v[3];
		v[2] = v[4], v[3] = v[5];
		v[4] = tmp0, v[5] = tmp1;
#endif
	}

	static void inverse_order_packs([[maybe_unused]] uint64_t* v) {
#if defined(USE_AVX512)
		uint64_t tmp0 = v[2], tmp1 = v[3];
		v[2] = v[4], v[3] = v[5];
		v[4] = v[8], v[5] = v[9];
		v[8] = tmp0, v[9] = tmp1;
		tmp0 = v[6], tmp1 = v[7];
		v[6] = v[12], v[7] = v[13];
		v[12] = v[10], v[13] = v[11];
		v[10] = tmp0, v[11] = tmp1;
#elif defined(USE_AVX2)  // Inverse _mm256_packs_epi16 ordering
		uint64_t tmp0 = v[2], tmp1 = v[3];
		v[2] = v[4], v[3] = v[5];
		v[4] = tmp0, v[5] = tmp1;
#endif
	}

	void permute_weights([[maybe_unused]] void (*order_fn)(uint64_t*)) const {
#if defined(USE_AVX2)
#if defined(USE_AVX512)
		constexpr IndexType di = 16;
#else
		constexpr IndexType di = 8;
#endif
		uint64_t* b = reinterpret_cast<uint64_t*>(const_cast<BiasType*>(&biases_[0]));
		for (IndexType i = 0; i < kHalfDimensions * sizeof(BiasType) / sizeof(uint64_t); i += di)
			order_fn(&b[i]);

		for (IndexType j = 0; j < kInputDimensions; ++j)
		{
			uint64_t* w =
				reinterpret_cast<uint64_t*>(const_cast<WeightType*>(&weights_[j * kHalfDimensions]));
			for (IndexType i = 0; i < kHalfDimensions * sizeof(WeightType) / sizeof(uint64_t);
					i += di)
				order_fn(&w[i]);
		}
#endif
	}

	inline void scale_weights(bool read) const {
		for (IndexType j = 0; j < kInputDimensions; ++j)
		{
			WeightType* w = const_cast<WeightType*>(&weights_[j * kHalfDimensions]);
			for (IndexType i = 0; i < kHalfDimensions; ++i)
				w[i] = read ? w[i] * 2 : w[i] / 2;
		}

		BiasType* b = const_cast<BiasType*>(biases_);
		for (IndexType i = 0; i < kHalfDimensions; ++i)
			b[i] = read ? b[i] * 2 : b[i] / 2;
	}

	// Calculate cumulative value without using difference calculation
	// 差分計算を用いずに累積値を計算する
	void refresh_accumulator(const Position& pos) const {
		auto& accumulator = pos.state()->accumulator;
		for (IndexType i = 0; i < kRefreshTriggers.size(); ++i) {
			Features::IndexList active_indices[2];
			RawFeatures::AppendActiveIndices(pos, kRefreshTriggers[i], active_indices);
			for (Color perspective : {BLACK, WHITE}) {
#if defined(VECTOR)
				if (i == 0) {
					std::memcpy(accumulator.accumulation[perspective][i], biases_, kHalfDimensions * sizeof(BiasType));
				} else {
					std::memset(accumulator.accumulation[perspective][i], 0, kHalfDimensions * sizeof(BiasType));
				}
				for (const auto index : active_indices[perspective]) {
					const IndexType offset = kHalfDimensions * index;
					auto accumulation      = reinterpret_cast<vec_t*>(&accumulator.accumulation[perspective][i][0]);
					auto column            = reinterpret_cast<const vec_t*>(&weights_[offset]);
					constexpr IndexType kNumChunks = kHalfDimensions / (sizeof(vec_t) / sizeof(BiasType));
					for (IndexType j = 0; j < kNumChunks; ++j) {
						accumulation[j] = vec_add_16(accumulation[j], column[j]);
					}
				}
#else
				if (i == 0) {
					std::memcpy(accumulator.accumulation[perspective][i], biases_, kHalfDimensions * sizeof(BiasType));
				} else {
					std::memset(accumulator.accumulation[perspective][i], 0, kHalfDimensions * sizeof(BiasType));
				}
				for (const auto index : active_indices[perspective]) {
					const IndexType offset = kHalfDimensions * index;

					for (IndexType j = 0; j < kHalfDimensions; ++j) {
						accumulator.accumulation[perspective][i][j] += weights_[offset + j];
					}
				}
#endif
			}
		}

		accumulator.computed_accumulation = true;
		// Stockfishでは fc27d15(2020-09-07) にcomputed_scoreが排除されているので確認
		accumulator.computed_score = false;
	}

	// Calculate cumulative value using difference calculation
	// 差分計算を用いて累積値を計算する
	void update_accumulator(const Position& pos) const {
		const auto prev_accumulator = pos.state()->previous->accumulator;
		auto&      accumulator      = pos.state()->accumulator;
		for (IndexType i = 0; i < kRefreshTriggers.size(); ++i) {
			Features::IndexList removed_indices[2], added_indices[2];
			bool                reset[2];
			RawFeatures::AppendChangedIndices(pos, kRefreshTriggers[i], removed_indices, added_indices, reset);
			for (Color perspective : {BLACK, WHITE}) {
#if defined(VECTOR)
				constexpr IndexType kNumChunks = kHalfDimensions / (sizeof(vec_t) / sizeof(BiasType));
				auto accumulation              = reinterpret_cast<vec_t*>(&accumulator.accumulation[perspective][i][0]);
#endif
				if (reset[perspective]) {
					if (i == 0) {
						std::memcpy(accumulator.accumulation[perspective][i], biases_,
						            kHalfDimensions * sizeof(BiasType));
					} else {
						std::memset(accumulator.accumulation[perspective][i], 0, kHalfDimensions * sizeof(BiasType));
					}
				} else {
					// Difference calculation for the feature amount changed from 1 to 0
					// 1から0に変化した特徴量に関する差分計算
					std::memcpy(accumulator.accumulation[perspective][i], prev_accumulator.accumulation[perspective][i],
					            kHalfDimensions * sizeof(BiasType));
					for (const auto index : removed_indices[perspective]) {
						const IndexType offset = kHalfDimensions * index;
#if defined(VECTOR)
						auto column = reinterpret_cast<const vec_t*>(&weights_[offset]);
						for (IndexType j = 0; j < kNumChunks; ++j) {
							accumulation[j] = vec_sub_16(accumulation[j], column[j]);
						}
#else
						for (IndexType j = 0; j < kHalfDimensions; ++j) {
							accumulator.accumulation[perspective][i][j] -= weights_[offset + j];
						}
#endif
					}
				}
				{
					// Difference calculation for features that changed from 0 to 1
					// 0から1に変化した特徴量に関する差分計算
					for (const auto index : added_indices[perspective]) {
						const IndexType offset = kHalfDimensions * index;
#if defined(VECTOR)
						auto column = reinterpret_cast<const vec_t*>(&weights_[offset]);
						for (IndexType j = 0; j < kNumChunks; ++j) {
							accumulation[j] = vec_add_16(accumulation[j], column[j]);
						}
#else
						for (IndexType j = 0; j < kHalfDimensions; ++j) {
							accumulator.accumulation[perspective][i][j] += weights_[offset + j];
						}
#endif
					}
				}
			}
		}

		accumulator.computed_accumulation = true;
		// Stockfishでは fc27d15(2020-09-07) にcomputed_scoreが排除されているので確認
		accumulator.computed_score = false;
	}

#if defined(SFNNwoPSQT) && defined(USE_NNUE_FINNY_TABLES)
	static constexpr IndexType kFinnyChunkSize =
#if defined(VECTOR)
		sizeof(vec_t) / sizeof(BiasType);
#else
		1;
#endif

	void add_weight(BiasType* accumulation, IndexType index) const {
		const IndexType offset = kHalfDimensions * index;
#if defined(VECTOR)
		static_assert(kHalfDimensions % kFinnyChunkSize == 0);
		constexpr IndexType kNumChunks = kHalfDimensions / kFinnyChunkSize;
		auto* acc = reinterpret_cast<vec_t*>(accumulation);
		const auto* column =
			reinterpret_cast<const vec_t*>(&weights_[offset]);
		for (IndexType j = 0; j < kNumChunks; ++j)
			acc[j] = vec_add_16(acc[j], column[j]);
#else
		for (IndexType j = 0; j < kHalfDimensions; ++j)
			accumulation[j] += weights_[offset + j];
#endif
	}

	void sub_weight(BiasType* accumulation, IndexType index) const {
		const IndexType offset = kHalfDimensions * index;
#if defined(VECTOR)
		static_assert(kHalfDimensions % kFinnyChunkSize == 0);
		constexpr IndexType kNumChunks = kHalfDimensions / kFinnyChunkSize;
		auto* acc = reinterpret_cast<vec_t*>(accumulation);
		const auto* column =
			reinterpret_cast<const vec_t*>(&weights_[offset]);
		for (IndexType j = 0; j < kNumChunks; ++j)
			acc[j] = vec_sub_16(acc[j], column[j]);
#else
		for (IndexType j = 0; j < kHalfDimensions; ++j)
			accumulation[j] -= weights_[offset + j];
#endif
	}

	void refresh_from_active_indices(
		IndexType trigger_idx, const Features::IndexList& active,
		BiasType* accumulation) const {
		if (trigger_idx == 0)
			std::memcpy(
				accumulation, biases_,
				kHalfDimensions * sizeof(BiasType));
		else
			std::memset(
				accumulation, 0,
				kHalfDimensions * sizeof(BiasType));

		for (const auto index : active)
			add_weight(accumulation, index);
	}

	static Square perspective_king_square(
		const Position& pos, Color perspective) {
		const auto square = pos.square<KING>(perspective);
		if (square < SQ_ZERO || square >= SQ_NB)
			return SQ_NONE;
		return perspective == BLACK ? square : Inv(square);
	}

	void apply_cache_diff(
		BiasType* accumulation,
		const IndexType* cached, IndexType cached_len,
		const IndexType* current, IndexType current_len) const {
		IndexType cached_pos = 0;
		IndexType current_pos = 0;

		while (cached_pos < cached_len && current_pos < current_len) {
			const auto cached_index = cached[cached_pos];
			const auto current_index = current[current_pos];
			if (cached_index < current_index) {
				sub_weight(accumulation, cached_index);
				++cached_pos;
			} else if (current_index < cached_index) {
				add_weight(accumulation, current_index);
				++current_pos;
			} else {
				++cached_pos;
				++current_pos;
			}
		}
		while (cached_pos < cached_len)
			sub_weight(accumulation, cached[cached_pos++]);
		while (current_pos < current_len)
			add_weight(accumulation, current[current_pos++]);
	}

	void refresh_from_available_active_indices(
		const Position& pos, Color perspective, IndexType trigger_idx,
		const Features::IndexList& active,
		BiasType* accumulation) const {
		if (active.size() != 0) {
			refresh_from_active_indices(
				trigger_idx, active, accumulation);
			return;
		}

		Features::IndexList generated[COLOR_NB];
		RawFeatures::AppendActiveIndices(
			pos, kRefreshTriggers[trigger_idx], generated);
		refresh_from_active_indices(
			trigger_idx, generated[perspective], accumulation);
	}

	void refresh_perspective_with_sorted_cache(
		const Position& pos, Color perspective, IndexType trigger_idx,
		const Features::IndexList& provided_active,
		Square king_square, BiasType* accumulation,
		FinnyTable& cache) const {
		Features::IndexList generated[COLOR_NB];
		const Features::IndexList* active = &provided_active;
		if (active->size() == 0) {
			RawFeatures::AppendActiveIndices(
				pos, kRefreshTriggers[trigger_idx], generated);
			active = &generated[perspective];
		}

		if (active->size() > kFinnyMaxActiveFeatures) {
			refresh_from_active_indices(
				trigger_idx, *active, accumulation);
			return;
		}

		IndexType sorted_active[kFinnyMaxActiveFeatures];
		const auto num_active =
			static_cast<IndexType>(active->size());
		std::copy(
			active->begin(), active->end(), sorted_active);
		std::sort(
			sorted_active, sorted_active + num_active);

		auto& entry =
			cache.entries[king_square][perspective];
		const bool cache_hit =
			entry.valid && !entry.piece_list_mode;
		if (cache_hit) {
			std::memcpy(
				accumulation, entry.accumulation,
				kHalfDimensions * sizeof(BiasType));
			apply_cache_diff(
				accumulation,
				entry.cache_keys, entry.num_active,
				sorted_active, num_active);
		} else {
			std::memcpy(
				accumulation, biases_,
				kHalfDimensions * sizeof(BiasType));
			for (IndexType i = 0; i < num_active; ++i)
				add_weight(accumulation, sorted_active[i]);
		}

		std::memcpy(
			entry.accumulation, accumulation,
			kHalfDimensions * sizeof(BiasType));
		std::copy(
			sorted_active, sorted_active + num_active,
			entry.cache_keys);
		entry.num_active =
			static_cast<std::uint16_t>(num_active);
		entry.piece_list_mode = false;
		entry.valid = true;
	}

	void refresh_perspective_with_cache(
		const Position& pos, Color perspective, IndexType trigger_idx,
		const Features::IndexList& active, BiasType* accumulation,
		FinnyTable& cache) const {
		static_assert(kRefreshTriggers.size() == 1);
		static_assert(
			kRefreshTriggers[0] ==
			Features::TriggerEvent::kFriendKingMoved);
		static_assert(
			kFinnyMaxActiveFeatures <=
			static_cast<IndexType>(UINT16_MAX));
		static_assert(
			kFinnyMaxActiveFeatures == PIECE_NUMBER_NB);

		if (trigger_idx != 0 ||
			(active.size() != 0 &&
			 active.size() > kFinnyMaxActiveFeatures)) {
			refresh_from_available_active_indices(
				pos, perspective, trigger_idx,
				active, accumulation);
			return;
		}

		const auto king_square =
			perspective_king_square(pos, perspective);
		if (king_square < SQ_ZERO || king_square >= SQ_NB) {
			refresh_from_available_active_indices(
				pos, perspective, trigger_idx,
				active, accumulation);
			return;
		}

		if constexpr (kUseFinnyPieceList) {
			using PieceFeature =
				Features::HalfKA_hm2<Features::Side::kFriend>;

			const auto* current_piece_list =
				perspective == BLACK
					? pos.eval_list()->piece_list_fb()
					: pos.eval_list()->piece_list_fw();

			auto& entry =
				cache.entries[king_square][perspective];
			if (entry.valid && entry.piece_list_mode) {
				std::memcpy(
					accumulation, entry.accumulation,
					kHalfDimensions * sizeof(BiasType));
				for (IndexType i = 0; i < PIECE_NUMBER_NB; ++i) {
					const auto cached_piece =
						static_cast<BonaPiece>(entry.cache_keys[i]);
					const auto current_piece = current_piece_list[i];
					if (cached_piece == current_piece)
						continue;
					if (current_piece == BONA_PIECE_ZERO) {
						refresh_perspective_with_sorted_cache(
							pos, perspective, trigger_idx,
							active, king_square,
							accumulation, cache);
						return;
					}

					sub_weight(
						accumulation,
						PieceFeature::MakeIndex(
							king_square, cached_piece));
					add_weight(
						accumulation,
						PieceFeature::MakeIndex(
							king_square, current_piece));
				}
			} else {
				std::memcpy(
					accumulation, biases_,
					kHalfDimensions * sizeof(BiasType));
				for (IndexType i = 0; i < PIECE_NUMBER_NB; ++i) {
					const auto piece = current_piece_list[i];
					if (piece == BONA_PIECE_ZERO) {
						refresh_perspective_with_sorted_cache(
							pos, perspective, trigger_idx,
							active, king_square,
							accumulation, cache);
						return;
					}
					add_weight(
						accumulation,
						PieceFeature::MakeIndex(
							king_square, piece));
				}
			}

			std::memcpy(
				entry.accumulation, accumulation,
				kHalfDimensions * sizeof(BiasType));
			for (IndexType i = 0; i < PIECE_NUMBER_NB; ++i)
				entry.cache_keys[i] =
					static_cast<IndexType>(current_piece_list[i]);
			entry.piece_list_mode = true;
			entry.valid = true;
		} else {
			refresh_perspective_with_sorted_cache(
				pos, perspective, trigger_idx,
				active, king_square, accumulation, cache);
		}
	}

	void refresh_accumulator_with_cache(
		const Position& pos, FinnyTable& cache) const {
		auto& accumulator = pos.state()->accumulator;
		for (IndexType i = 0; i < kRefreshTriggers.size(); ++i) {
			if constexpr (kUseFinnyPieceList) {
				Features::IndexList unused_active;
				for (Color perspective : COLOR)
					refresh_perspective_with_cache(
						pos, perspective, i, unused_active,
						accumulator.accumulation[perspective][i],
						cache);
			} else {
				Features::IndexList active_indices[COLOR_NB];
				RawFeatures::AppendActiveIndices(
					pos, kRefreshTriggers[i], active_indices);
				for (Color perspective : COLOR)
					refresh_perspective_with_cache(
						pos, perspective, i,
						active_indices[perspective],
						accumulator.accumulation[perspective][i],
						cache);
			}
		}
		accumulator.computed_accumulation = true;
		accumulator.computed_score = false;
	}

	void update_accumulator_with_cache(
		const Position& pos, FinnyTable& cache) const {
		const auto& prev_accumulator =
			pos.state()->previous->accumulator;
		auto& accumulator = pos.state()->accumulator;

		for (IndexType i = 0; i < kRefreshTriggers.size(); ++i) {
			Features::IndexList removed_indices[COLOR_NB];
			Features::IndexList added_indices[COLOR_NB];
			bool reset[COLOR_NB] = {};
			RawFeatures::AppendChangedIndices(
				pos, kRefreshTriggers[i],
				removed_indices, added_indices, reset);

			for (Color perspective : COLOR) {
				auto* current =
					accumulator.accumulation[perspective][i];
				if (reset[perspective]) {
					// For a reset, AppendChangedIndices has already
					// populated added_indices with every active feature.
					refresh_perspective_with_cache(
						pos, perspective, i,
						added_indices[perspective],
						current, cache);
					continue;
				}

				std::memcpy(
					current,
					prev_accumulator.accumulation[perspective][i],
					kHalfDimensions * sizeof(BiasType));
				for (const auto index :
					removed_indices[perspective])
					sub_weight(current, index);
				for (const auto index :
					added_indices[perspective])
					add_weight(current, index);
			}
		}

		accumulator.computed_accumulation = true;
		accumulator.computed_score = false;
	}
#endif

	// parameter type
	// パラメータの型

	// parameter
	// パラメータ
	alignas(kCacheLineSize) BiasType biases_[kHalfDimensions];
	alignas(kCacheLineSize) WeightType weights_[kHalfDimensions * kInputDimensions];
};

} // namespace Eval::NNUE
} // namespace YaneuraOu

#endif  // defined(EVAL_NNUE)

#endif  // #ifndef NNUE_FEATURE_TRANSFORMER_H_INCLUDED
