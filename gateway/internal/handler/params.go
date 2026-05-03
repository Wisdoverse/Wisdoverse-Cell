package handler

import (
	"math"
	"strconv"
)

func parsePageParam(value string) int32 {
	page, err := strconv.ParseInt(value, 10, 64)
	if err != nil || page < 1 || page > math.MaxInt32 {
		return 1
	}
	return int32(page)
}

func parsePageActionValue(value any) int32 {
	page, ok := value.(float64)
	if !ok || page < 1 || page > math.MaxInt32 || math.Trunc(page) != page {
		return 1
	}
	return int32(page)
}
