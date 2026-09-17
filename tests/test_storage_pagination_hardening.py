from types import SimpleNamespace
import unittest

from storage_pagination_hardening import (
    StoragePaginationError,
    install_storage_pagination_hardening,
    iter_s3_pages,
)


class FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        self.deleted = []

    def list_objects_v2(self, **kwargs):
        self.calls.append(dict(kwargs))
        if not self.pages:
            raise AssertionError("unexpected extra pagination call")
        return self.pages.pop(0)

    def delete_objects(self, **kwargs):
        self.deleted.append(dict(kwargs))
        return {}


class StoragePaginationHardeningTests(unittest.TestCase):
    def test_iterates_normal_pages_and_passes_continuation_token(self):
        client = FakeClient([
            {
                "Contents": [{"Key": "a"}],
                "IsTruncated": True,
                "NextContinuationToken": "next-1",
            },
            {
                "Contents": [{"Key": "b"}],
                "IsTruncated": False,
            },
        ])

        pages = list(iter_s3_pages(client, "bucket", prefix="materials/x/"))

        self.assertEqual(len(pages), 2)
        self.assertNotIn("ContinuationToken", client.calls[0])
        self.assertEqual(client.calls[1]["ContinuationToken"], "next-1")
        self.assertEqual(client.calls[0]["Prefix"], "materials/x/")

    def test_missing_next_token_fails_closed(self):
        client = FakeClient([
            {"Contents": [], "IsTruncated": True},
        ])

        with self.assertRaisesRegex(StoragePaginationError, "continuation token"):
            list(iter_s3_pages(client, "bucket"))

        self.assertEqual(len(client.calls), 1)

    def test_repeated_token_is_stopped_before_third_request(self):
        client = FakeClient([
            {
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "same-token",
            },
            {
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "same-token",
            },
        ])

        with self.assertRaisesRegex(StoragePaginationError, "重複"):
            list(iter_s3_pages(client, "bucket"))

        self.assertEqual(len(client.calls), 2)

    def test_max_page_guard_stops_unique_never_ending_sequence(self):
        client = FakeClient([
            {
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "token-1",
            },
            {
                "Contents": [],
                "IsTruncated": True,
                "NextContinuationToken": "token-2",
            },
        ])

        with self.assertRaisesRegex(StoragePaginationError, "安全上限"):
            list(iter_s3_pages(client, "bucket", max_pages=2))

        self.assertEqual(len(client.calls), 2)

    def test_install_replaces_r2_delete_with_guarded_idempotent_batches(self):
        client = FakeClient([
            {
                "Contents": [{"Key": "materials/1/a"}],
                "IsTruncated": True,
                "NextContinuationToken": "page-2",
            },
            {
                "Contents": [{"Key": "materials/1/b"}],
                "IsTruncated": False,
            },
        ])
        recorded = []
        base = SimpleNamespace(
            R2_BUCKET_NAME="r2-bucket",
            OCI_BUCKET_NAME="oci-bucket",
            r2_client=lambda: client,
            oci_client=lambda: client,
            r2_record_deleted=recorded.append,
        )

        install_storage_pagination_hardening(base)
        base.r2_delete_prefix("materials/1/")

        self.assertEqual(recorded, ["materials/1/a", "materials/1/b"])
        self.assertEqual(len(client.deleted), 2)
        self.assertTrue(base._storage_pagination_hardening_installed)

    def test_install_hardens_oci_usage_listing_too(self):
        client = FakeClient([
            {
                "Contents": [{"Key": "a", "Size": 7}],
                "IsTruncated": True,
                "NextContinuationToken": "page-2",
            },
            {
                "Contents": [{"Key": "b", "Size": 11}],
                "IsTruncated": False,
            },
        ])
        base = SimpleNamespace(
            R2_BUCKET_NAME="r2-bucket",
            OCI_BUCKET_NAME="oci-bucket",
            r2_client=lambda: client,
            oci_client=lambda: client,
            r2_record_deleted=lambda _key: None,
        )

        install_storage_pagination_hardening(base)

        self.assertEqual(base.oci_bucket_usage_bytes(), 18)


if __name__ == "__main__":
    unittest.main()
