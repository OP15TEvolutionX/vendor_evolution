package generator

import (
	"fmt"

	"android/soong/android"
)

func lineageExpandVariables(ctx android.ModuleContext, in string) string {
	lineageVars := ctx.Config().VendorConfig("lineageVarsPlugin")

	out, err := android.Expand(in, func(name string) (string, error) {
		if lineageVars.IsSet(name) {
			return lineageVars.String(name), nil
		}
		switch name {
		case "KERNEL_ARCH",
			"KERNEL_BUILD_OUT_PREFIX",
			"KERNEL_CROSS_COMPILE",
			"KERNEL_MAKE_CMD",
			"KERNEL_MAKE_FLAGS",
			"KERNEL_PATH",
			"PATH_OVERRIDE_SOONG",
			"TARGET_KERNEL_CONFIG",
			"TARGET_KERNEL_SOURCE",
			"TARGET_KERNEL_PLATFORM_TARGET",
			"TARGET_MAX_PAGE_SIZE_SUPPORTED",
			"TARGET_PREBUILT_KERNEL_HEADERS":
			return "", nil
		}
		// This variable is not for us, restore what the original
		// variable string will have looked like for an Expand
		// that comes later.
		return fmt.Sprintf("$(%s)", name), nil
	})

	if err != nil {
		ctx.PropertyErrorf("%s: %s", in, err.Error())
		return ""
	}

	return out
}
