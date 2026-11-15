import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PATHS } from '../lib/paths.ts'
import type { Room } from '../types/room.ts'
import Avatar from './Avatar.tsx'
import Badge from './Badge.tsx'
import Icon from './Icon.tsx'
import YieldSteps from './YieldSteps.tsx'
import styles from './TeamSection.module.css'

// 나 탭의 팀: 팀원 목록과 사람별 누적 양보 단계, 초대 코드.
// 역할은 보여 주지 않고 팀장 뱃지만 붙인다. 누적 양보는 숫자 없이 단계로만 보인다.
export default function TeamSection({ room }: { room: Room }) {
  return (
    <>
      <section className="sec">
        <div className="row-between">
          <h2>
            팀원{' '}
            <span className="meta num">
              {room.joinedCount}/{room.memberCount} 들어옴
            </span>
          </h2>
          <Link to={`${PATHS.meActivity}?tab=yield`} className="btn small">
            양보 기록 보기
          </Link>
        </div>
        <ul className={styles.list}>
          {room.members.map((m) => (
            <li key={m.id} className={styles.member}>
              <Avatar name={m.name} size="large" />
              <span className={styles.name}>
                <span className="strong">
                  {m.name}
                  {m.isMe && ' (나)'}
                </span>
                {m.isLeader && <Badge tone="here">팀장</Badge>}
              </span>
              <span className={styles.yield}>
                <YieldSteps level={m.yieldLevel} />
                <span className="meta">{m.yieldLevel}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="sec">
        <h2>팀원 초대</h2>
        <div className={styles.codeRow}>
          <span className={`${styles.code} num`}>{room.inviteCode}</span>
          <CopyButton text={room.inviteCode} />
        </div>
      </section>
    </>
  )
}

// 초대 코드 복사 아이콘. 복사되면 잠깐 체크로 바뀐다. 복사가 막힌 브라우저에서는 코드를 보고 직접 알려 주면 된다
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  return (
    <button type="button" className={styles.copy} onClick={copy} aria-label={copied ? '복사했어요' : '초대 코드 복사'}>
      <Icon name={copied ? 'check' : 'copy'} small />
    </button>
  )
}
