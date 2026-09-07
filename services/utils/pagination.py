from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    """
    Standard pagination for the project. Since every endpoint returns its
    response via ResponseHandler (not DRF's default paginated Response),
    views call `self.paginator.get_meta()` to build the meta block themselves
    instead of using get_paginated_response().
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_meta(self) -> dict:
        return {
            'page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'total': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
        }
