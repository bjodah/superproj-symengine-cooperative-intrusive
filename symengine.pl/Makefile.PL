use strict;
use warnings;

use Config;
use ExtUtils::MakeMaker;
use File::Spec;
use FindBin;

sub abs_dir {
    my ($path) = @_;
    return File::Spec->rel2abs($path);
}

my $project_root = abs_dir(File::Spec->catdir($FindBin::Bin || '.', '..'));
my $symengine_source = abs_dir($ENV{SYMENGINE_SOURCE_DIR}
    || File::Spec->catdir($project_root, 'symengine'));
my $symengine_build = abs_dir($ENV{SYMENGINE_BUILD_DIR}
    || File::Spec->catdir($project_root, 'build-perl', 'symengine'));

my @include_dirs = (
    $symengine_source,
    $symengine_build,
    File::Spec->catdir($symengine_source, 'symengine', 'utilities', 'cereal', 'include'),
);

if (defined $ENV{NANOBIND_INCLUDE_DIR} && length $ENV{NANOBIND_INCLUDE_DIR}) {
    push @include_dirs, $ENV{NANOBIND_INCLUDE_DIR};
}

my @lib_dirs = grep { -d $_ } (
    File::Spec->catdir($symengine_build, 'symengine'),
    $symengine_build,
    File::Spec->catdir($symengine_build, '..', 'symengine', 'symengine'),
);

my $inc = join ' ', map { '-I' . $_ } @include_dirs;
my $extra_libs = $ENV{SYMENGINE_EXTRA_LIBS} || '-lgmp';
my $libs = join ' ', (map { '-L' . $_ } @lib_dirs), '-lsymengine', $extra_libs;
my $cxx = $ENV{CXX} || $Config{cxx} || 'c++';

WriteMakefile(
    NAME          => 'SymEngine',
    VERSION_FROM  => 'lib/SymEngine.pm',
    ABSTRACT      => 'Minimal Perl XS wrapper for SymEngine',
    AUTHOR        => 'SymEngine contributors',
    LICENSE       => 'perl_5',
    MIN_PERL_VERSION => '5.020',
    CONFIGURE_REQUIRES => {
        'ExtUtils::MakeMaker' => 0,
    },
    TEST_REQUIRES => {
        'Test::More' => 0,
    },
    XS            => { 'xs/SymEngine.xs' => 'xs/SymEngine.c' },
    OBJECT        => 'SymEngine$(OBJ_EXT) perl_symengine$(OBJ_EXT)',
    INC           => $inc,
    LIBS          => [$libs],
    CC            => $cxx,
    LD            => $cxx,
    XSOPT         => '-C++',
    DEFINE        => '',
    CCFLAGS       => "$Config{ccflags} -std=c++17",
);

sub MY::postamble {
    return <<'MAKE';

SymEngine$(OBJ_EXT): xs/SymEngine.c
	$(CCCMD) $(CCCDLFLAGS) "-I$(PERL_INC)" xs/SymEngine.c

perl_symengine$(OBJ_EXT): xs/perl_symengine.cpp xs/perl_symengine.h
	$(CCCMD) $(CCCDLFLAGS) "-I$(PERL_INC)" xs/perl_symengine.cpp

MAKE
}
