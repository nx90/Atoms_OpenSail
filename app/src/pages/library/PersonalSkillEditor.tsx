import { ArrowLeft, LockKey, Trash } from '@phosphor-icons/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import CodeEditor from '../../components/CodeEditor';
import { personalSkillsApi, type PersonalSkillSummary } from '../../lib/api';
import type { FileTreeEntry } from '../../utils/buildFileTree';

interface PersonalSkillEditorProps {
  skill: PersonalSkillSummary;
  onClose: () => void;
  onChanged: (skill: PersonalSkillSummary) => void;
  onDeleted: (skillId: string) => void;
}

export default function PersonalSkillEditor({
  skill,
  onClose,
  onChanged,
  onDeleted,
}: PersonalSkillEditorProps) {
  const [fileTree, setFileTree] = useState<FileTreeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const revisionRef = useRef(skill.revision);
  const onChangedRef = useRef(onChanged);
  const mutationQueueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    revisionRef.current = skill.revision;
  }, [skill.revision]);

  useEffect(() => {
    onChangedRef.current = onChanged;
  }, [onChanged]);

  const refresh = useCallback(async () => {
    const result = await personalSkillsApi.tree(skill.id);
    revisionRef.current = result.skill.revision;
    setFileTree(
      result.entries.map((entry) => ({
        path: entry.path,
        name: entry.path.split('/').pop() || entry.path,
        is_dir: entry.is_directory,
        size: entry.size_bytes,
        mod_time: entry.updated_at ? Date.parse(entry.updated_at) / 1000 : 0,
      }))
    );
    onChangedRef.current(result.skill);
  }, [skill.id]);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch(() => toast.error('Failed to load skill files'))
      .finally(() => setLoading(false));
  }, [refresh]);

  const enqueueMutation = useCallback(
    (operation: (revision: number) => Promise<PersonalSkillSummary>) => {
      mutationQueueRef.current = mutationQueueRef.current
        .then(async () => {
          const updated = await operation(revisionRef.current);
          revisionRef.current = updated.revision;
          await refresh();
        })
        .catch((error) => {
          const status = error?.response?.status;
          const detail = error?.response?.data?.detail;
          if (status === 409) {
            toast.error(
              detail || 'This skill changed elsewhere. Your unsaved editor buffer was kept.'
            );
            void refresh();
            return;
          }
          toast.error(detail || 'Skill update failed');
        });
    },
    [refresh]
  );

  const handleDeleteSkill = async () => {
    if (!window.confirm(`Delete “${skill.name}” and all of its files?`)) return;
    try {
      await personalSkillsApi.remove(skill.id);
      onDeleted(skill.id);
      toast.success('Skill deleted');
    } catch (error: unknown) {
      const apiError = error as { response?: { data?: { detail?: string } } };
      toast.error(apiError.response?.data?.detail || 'Failed to delete skill');
    }
  };

  return (
    <div className="h-full flex flex-col bg-[var(--bg)]">
      <div className="h-12 px-3 flex items-center gap-3 border-b border-[var(--border)] shrink-0">
        <button type="button" onClick={onClose} className="btn btn-icon" title="Back to skills">
          <ArrowLeft size={16} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-[var(--text)] truncate">{skill.name}</h2>
            <span className="text-[10px] px-1.5 py-0.5 border border-[var(--border)] text-[var(--text-muted)]">
              Personal
            </span>
          </div>
          <p className="text-[11px] text-[var(--text-subtle)] truncate">
            {skill.description ||
              'Edit SKILL.md frontmatter to describe when agents should use it.'}
          </p>
        </div>
        <div className="hidden sm:flex items-center gap-1 text-[10px] text-[var(--text-subtle)]">
          <LockKey size={13} /> Private · revision {revisionRef.current}
        </div>
        <button
          type="button"
          onClick={handleDeleteSkill}
          className="btn btn-icon btn-danger"
          title="Delete skill"
        >
          <Trash size={15} />
        </button>
      </div>

      <div className="flex-1 min-h-0">
        <CodeEditor
          key={skill.id}
          fileTree={fileTree}
          isFilesSyncing={loading}
          protectedPaths={['SKILL.md']}
          loadFileContent={async (path) => {
            const result = await personalSkillsApi.readFile(skill.id, path);
            return { content: result.content };
          }}
          onFileUpdate={(path, content) =>
            enqueueMutation(async (revision) => {
              const result = await personalSkillsApi.writeFile(skill.id, path, content, revision);
              return result.skill;
            })
          }
          onFileCreate={(path) =>
            enqueueMutation(async (revision) => {
              const result = await personalSkillsApi.writeFile(skill.id, path, '', revision);
              return result.skill;
            })
          }
          onDirectoryCreate={(path) =>
            enqueueMutation((revision) =>
              personalSkillsApi.createDirectory(skill.id, path, revision)
            )
          }
          onFileRename={(oldPath, newPath) =>
            enqueueMutation((revision) =>
              personalSkillsApi.renameEntry(skill.id, oldPath, newPath, revision)
            )
          }
          onFileDelete={(path) =>
            enqueueMutation((revision) => personalSkillsApi.deleteEntry(skill.id, path, revision))
          }
        />
      </div>
    </div>
  );
}
