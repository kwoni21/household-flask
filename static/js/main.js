// static/js/main.js

// ── 천단위 자동 포맷 ────────────────────────────────────────
document.querySelectorAll('.amount-input').forEach(input => {
  input.addEventListener('input', function () {
    // 숫자만 추출
    const raw = this.value.replace(/[^0-9]/g, '');
    // hidden input에 raw 값 저장
    const hiddenId = this.dataset.target;
    if (hiddenId) document.getElementById(hiddenId).value = raw;
    // 천단위 쉼표 포맷으로 표시
    this.value = raw ? parseInt(raw).toLocaleString('ko-KR') : '';
  });

  // 페이지 로드 시 기존 값 포맷
  if (input.value) {
    const raw = input.value.replace(/[^0-9]/g, '');
    input.value = raw ? parseInt(raw).toLocaleString('ko-KR') : '';
  }
});

// ── 아이디 저장 (localStorage) ──────────────────────────────
const useridInput  = document.getElementById('userid');
const rememberChk  = document.getElementById('remember');
const loginForm    = document.getElementById('login-form');

if (useridInput && rememberChk) {
  // 페이지 로드 시 저장된 아이디 불러오기
  const savedId = localStorage.getItem('household_userid');
  if (savedId) {
    useridInput.value  = savedId;
    rememberChk.checked = true;
  }

  // 로그인 시 아이디 저장/삭제
  if (loginForm) {
    loginForm.addEventListener('submit', function () {
      if (rememberChk.checked) {
        localStorage.setItem('household_userid', useridInput.value);
      } else {
        localStorage.removeItem('household_userid');
      }
    });
  }
}

// ── 삭제 확인 ───────────────────────────────────────────────
document.querySelectorAll('.delete-form').forEach(form => {
  form.addEventListener('submit', function (e) {
    if (!confirm('이 거래를 삭제할까요?')) e.preventDefault();
  });
});
