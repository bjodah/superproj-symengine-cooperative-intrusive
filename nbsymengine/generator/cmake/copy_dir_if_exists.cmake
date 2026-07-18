# copy_dir_if_exists.cmake -- Copy a directory if it exists, create target if not.
# Usage: cmake -DSRC_DIR=<source> -DDST_DIR=<destination> -P copy_dir_if_exists.cmake

if(IS_DIRECTORY "${SRC_DIR}")
    file(COPY "${SRC_DIR}/" DESTINATION "${DST_DIR}")
else()
    file(MAKE_DIRECTORY "${DST_DIR}")
endif()
