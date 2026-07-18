package SymEngine;

use strict;
use warnings;

our $VERSION = '0.001';

require XSLoader;
XSLoader::load('SymEngine', $VERSION);

package SymEngine::Basic;

use strict;
use warnings;
use overload
    '""' => sub { SymEngine::Basic::_stringify($_[0]) },
    '==' => sub { SymEngine::Basic::_equals($_[0], $_[1]) },
    'eq' => sub { SymEngine::Basic::_equals($_[0], $_[1]) },
    fallback => 1;

sub stringify { SymEngine::Basic::_stringify($_[0]) }
sub equals { SymEngine::Basic::_equals($_[0], $_[1]) }

1;
