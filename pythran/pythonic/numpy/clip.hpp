#ifndef PYTHONIC_NUMPY_CLIP_HPP
#define PYTHONIC_NUMPY_CLIP_HPP

#include "pythonic/utils/proxy.hpp"
#include "pythonic/types/ndarray.hpp"

namespace pythonic {

    namespace numpy {
        template<class I, class O, class Mi, class Ma>
            void _clip(I begin, I end, O& out, Mi a_min, Ma a_max, utils::int_<1>)
            {
                for(; begin != end; ++ begin, ++out) {
                    auto v = *begin;
                    if(v<a_min) v=a_min;
                    else if(v>a_max) v = a_max;
                    *out = v;
                }
            }
        template<class I, class O, class Mi, class Ma, size_t N>
            void _clip(I begin, I end, O& out, Mi a_min, Ma a_max, utils::int_<N>)
            {
                for(; begin != end; ++ begin)
                    _clip((*begin).begin(), (*begin).end(), out, a_min, a_max, utils::int_<N - 1>());
            }
        template<class E, class Mi, class Ma>
            typename types::numpy_expr_to_ndarray<E>::type clip(E const& e, Mi a_min, Ma a_max) {
                typename types::numpy_expr_to_ndarray<E>::type out(e.shape, __builtin__::None);
                auto out_iter = out.fbegin();
                _clip(e.begin(), e.end(), out_iter, a_min, a_max, utils::int_<types::numpy_expr_to_ndarray<E>::N>());
                return out;
            }

        PROXY(pythonic::numpy, clip);

    }

}

#endif

