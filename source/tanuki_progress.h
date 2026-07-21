#ifndef TANUKI_PROGRESS_H_INCLUDED
#define TANUKI_PROGRESS_H_INCLUDED

#include "evaluate.h"
#include "usioption.h"

namespace YaneuraOu {
class IEngine;
class Position;
namespace Test {
class UnitTester;
}
}

namespace Tanuki {
namespace Progress {

enum class BucketMode {
    First,
    KingRank9,
    Progress8KPAbs,
    Progress8Ek,
};

bool add_options(YaneuraOu::OptionsMap& options);
void SetLayerStackCount(int layer_stacks);
BucketMode CurrentBucketMode();
bool Load();
int LayerStackIndex(const YaneuraOu::Position& pos);
bool IsMutualEnteringKing(const YaneuraOu::Position& pos);
int LayerStackIndexProgress8Ek(const YaneuraOu::Position& pos);
void UnitTest(YaneuraOu::Test::UnitTester& tester, YaneuraOu::IEngine& engine);

}  // namespace Progress
}  // namespace Tanuki

#endif  // TANUKI_PROGRESS_H_INCLUDED
