cmake_minimum_required(VERSION 3.18)

if (NOT SYMENGINE_RCP_BACKEND STREQUAL "symengine")
    message(FATAL_ERROR
        "BUILD_JAVA_JNI requires SYMENGINE_RCP_BACKEND=symengine; Java uses ordinary RCP handles")
endif ()
if (NOT WITH_SYMENGINE_THREAD_SAFE)
    message(FATAL_ERROR
        "BUILD_JAVA_JNI requires WITH_SYMENGINE_THREAD_SAFE=ON for Cleaner threads")
endif ()

find_package(Java 21 REQUIRED COMPONENTS Development)
find_package(JNI REQUIRED COMPONENTS JVM)
include(UseJava)
find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(SYMENGINE_JAVA_GENERATED_DIR "${CMAKE_BINARY_DIR}/binding-generated/java")
set(SYMENGINE_JAVA_GENERATED_JNI "${SYMENGINE_JAVA_GENERATED_DIR}/SymEngineJNI.java")
set(SYMENGINE_JAVA_GENERATED_API "${SYMENGINE_JAVA_GENERATED_DIR}/SymEngine.java")
set(SYMENGINE_JAVA_GENERATED_CPP "${SYMENGINE_JAVA_GENERATED_DIR}/symengine_jni_generated.cpp")
set(SYMENGINE_JAVA_GENERATED_SHARED_TEST "${SYMENGINE_JAVA_GENERATED_DIR}/SharedCasesTest.java")
get_target_property(SYMENGINE_JAVA_SYMENGINE_INCLUDE_DIRS symengine INCLUDE_DIRECTORIES)

symengine_binding_codegen(
    LANGUAGE java
    OUTPUT_DIR "${SYMENGINE_JAVA_GENERATED_DIR}"
    OUTPUTS "${SYMENGINE_JAVA_GENERATED_JNI}" "${SYMENGINE_JAVA_GENERATED_API}"
            "${SYMENGINE_JAVA_GENERATED_CPP}" "${SYMENGINE_JAVA_GENERATED_SHARED_TEST}"
    TARGET symengine_java_generated
    PYTHON "${Python3_EXECUTABLE}"
    COMMENT "Generating Java JNI binding surface")

set(SYMENGINE_JAVA_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/main/java")
set(CMAKE_JAVA_COMPILE_FLAGS --release 21)
add_jar(symengine_java
    SOURCES
        "${SYMENGINE_JAVA_SOURCE_DIR}/org/symengine/Basic.java"
        "${SYMENGINE_JAVA_SOURCE_DIR}/org/symengine/SymEngineException.java"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/test/java/org/symengine/SmokeTest.java"
        "${SYMENGINE_JAVA_GENERATED_JNI}"
        "${SYMENGINE_JAVA_GENERATED_API}"
        "${SYMENGINE_JAVA_GENERATED_SHARED_TEST}")
add_dependencies(symengine_java symengine_java_generated)

add_library(symengine_jni SHARED
    src/main/native/symengine_jni.cpp
    "${SYMENGINE_JAVA_GENERATED_CPP}")
add_dependencies(symengine_jni symengine_java_generated)
target_compile_features(symengine_jni PRIVATE cxx_std_20)
target_include_directories(symengine_jni PRIVATE
    "${CMAKE_SOURCE_DIR}/symengine"
    "${CMAKE_BINARY_DIR}/symengine"
    ${SYMENGINE_JAVA_SYMENGINE_INCLUDE_DIRS}
    "${CMAKE_CURRENT_SOURCE_DIR}/src/main/native"
    "${SYMENGINE_JAVA_GENERATED_DIR}")
target_link_libraries(symengine_jni PRIVATE symengine JNI::JNI)

add_test(NAME java_symengine
    COMMAND "${Java_JAVA_EXECUTABLE}" -ea -Xcheck:jni
            --enable-native-access=ALL-UNNAMED
            "-Djava.library.path=$<TARGET_FILE_DIR:symengine_jni>"
            -cp "$<TARGET_PROPERTY:symengine_java,JAR_FILE>"
            org.symengine.SmokeTest)
set_tests_properties(java_symengine PROPERTIES DEPENDS symengine_java)

add_test(NAME java_symengine_shared_cases
    COMMAND "${Java_JAVA_EXECUTABLE}" -ea -Xcheck:jni
            --enable-native-access=ALL-UNNAMED
            "-Djava.library.path=$<TARGET_FILE_DIR:symengine_jni>"
            -cp "$<TARGET_PROPERTY:symengine_java,JAR_FILE>"
            org.symengine.SharedCasesTest)
set_tests_properties(java_symengine_shared_cases PROPERTIES DEPENDS symengine_java)
