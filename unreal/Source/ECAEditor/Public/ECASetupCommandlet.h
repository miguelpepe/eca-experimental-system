#pragma once

#include "Commandlets/Commandlet.h"
#include "ECASetupCommandlet.generated.h"

// connect the voice manager to the configured backend
UCLASS()
class ECAEDITOR_API UECASetupCommandlet : public UCommandlet
{
    GENERATED_BODY()

public:
    UECASetupCommandlet();
    virtual int32 Main(const FString& Params) override;
};
