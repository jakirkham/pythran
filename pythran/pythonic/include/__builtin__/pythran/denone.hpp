#ifndef PYTHONIC_INCLUDE_BUILTIN_PYTHRAN_DENONE_HPP
#define PYTHONIC_INCLUDE_BUILTIN_PYTHRAN_DENONE_HPP

#include "pythonic/include/utils/functor.hpp"
#include "pythonic/include/types/NoneType.hpp"

namespace pythonic
{

  namespace __builtin__
  {

    namespace pythran
    {

      template <class T>
      T denone(types::none<T> &&v);
      template <class T>
      T denone(types::none<T> const &v);
      template <class T>
      T denone(types::none<T> &v);

      template <class T>
      T denone(T v);

      DECLARE_FUNCTOR(pythonic::__builtin__::pythran, denone);
    }
  }
}

#endif
