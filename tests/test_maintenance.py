"""Pure recovery filename regression checks; no native package operations."""
import unittest
from native.maintenance import archive_names


class RecoveryNames(unittest.TestCase):
    def test_epoch_is_retained_as_in_arch_repository_filename(self):
        self.assertEqual(archive_names('docker', '1:29.8.2-1')[0],
                         'docker-1:29.8.2-1-x86_64.pkg.tar.zst')

    def test_both_official_architectures_are_considered(self):
        self.assertEqual(archive_names('cloud-image-utils', '0.33-3'),
                         ['cloud-image-utils-0.33-3-x86_64.pkg.tar.zst',
                          'cloud-image-utils-0.33-3-any.pkg.tar.zst'])

    def test_path_or_shell_inputs_are_rejected(self):
        for value in ('../x', '$(id)', 'a/b', 'a\nb'):
            with self.assertRaises(ValueError):
                archive_names(value, '1-1')


if __name__ == '__main__':
    unittest.main()
