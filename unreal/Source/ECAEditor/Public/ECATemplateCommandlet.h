#pragma once

#include "Commandlets/Commandlet.h"
#include "ECATemplateCommandlet.generated.h"

// create the portable scene and keep local startup preferences
UCLASS()
class ECAEDITOR_API UECATemplateCommandlet : public UCommandlet
{
    GENERATED_BODY()
public:
    UECATemplateCommandlet();
    virtual int32 Main(const FString& Params) override;
};
