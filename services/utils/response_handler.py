from rest_framework.response import Response


class ResponseHandler(Response):
    """
    Wraps DRF's Response so every endpoint returns the same shape:
    {success, data, message, errors, meta}.
    """

    def __init__(self, data=None, success=True, status=None,
                 message=None, meta=None, headers=None,
                 errors=None, content_type=None):
        resp_data = {'success': success}
        if data is not None:
            resp_data['data'] = data
        if message:
            resp_data['message'] = message
        if meta:
            resp_data['meta'] = meta
        if errors:
            resp_data['errors'] = errors
        super().__init__(resp_data, status=status, headers=headers, content_type=content_type)
