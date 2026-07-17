# Host-side build for FW-VECTOR-01B App modules (target build is CubeIDE).
#   cmake -B build && cmake --build build && ctest --test-dir build
cmake_minimum_required(VERSION 3.16)
project(fw_vector_app C)

set(CMAKE_C_STANDARD 11)
add_compile_options(-Wall -Wextra -Werror)

add_library(vx_app
    App/vx_param_store.c
    App/vx_nv_store.c
    App/vx_telemetry.c
    App/vx_device.c
)
target_include_directories(vx_app PUBLIC
    App
    ${CMAKE_CURRENT_SOURCE_DIR}/../PROTO-VORTEX-01A/generated
)

enable_testing()
add_executable(test_app tests/test_app.c)
target_link_libraries(test_app vx_app m)
add_test(NAME app_tests COMMAND test_app)
